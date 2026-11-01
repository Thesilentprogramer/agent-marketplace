"""The TextQL agent service: the contract every remote agent speaks.

  GET  /health                 200 {"ok": true} when it can work
  POST /ask {"question": "..."}  200 {"answer", "costUsd", "tokensIn", "tokensOut", "charts"}
  POST /check {} or {"values": {...}}  200 {"state": "ok" | "refused" | "unreachable", "detail"}
  anything wrong               non-200 {"error": "..."}

Settings come from the environment the client's settings service starts it
with: TEXTQL_API_KEY, TEXTQL_CONNECTOR_IDS, TEXTQL_BASE_URL, PORT.

  python -m textql_agent.server
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from textql_agent.log import log, redact
from textql_agent.reader import TEXTQL_TIMEOUT_SECONDS, TextQLAnswer, TextQLError, TextQLReader, connector_ids


# A question is a sentence; anything larger is refused unread.
MAX_BODY_BYTES = 1_000_000


# POST /check, as agent_kit/login.py answers it for the other agents (this image
# is built from agents/textql alone, so it cannot use the kit): only a refusal
# TextQL makes plain is "refused"; anything unforeseen is "unreachable".
OK, REFUSED, UNREACHABLE = "ok", "refused", "unreachable"
STATES = (OK, REFUSED, UNREACHABLE)
CHECK_TIMEOUT_SECONDS = 15.0


def _result(state: str, detail: str = "") -> dict[str, str]:
    return {"state": state, "detail": redact(detail, 300)}


def check_login(values: Mapping[str, str], client: httpx.Client | None = None) -> dict[str, str]:
    """One list of the data connections the key can use (GET /v2/connectors):
    a 401 refuses the key. A configured connection missing from the list is
    "unreachable" (not checked) until that reading has been tried against a
    real account: a false refusal would turn a working agent off."""
    key = (values.get("TEXTQL_API_KEY") or "").strip()
    if not key or "replace" in key.lower():
        return _result(REFUSED, "TEXTQL_API_KEY is not set")
    base = (values.get("TEXTQL_BASE_URL") or "https://app.textql.com").rstrip("/")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if client is None:
        with httpx.Client(timeout=CHECK_TIMEOUT_SECONDS) as own:
            response = own.get(f"{base}/v2/connectors", headers=headers)
    else:
        response = client.get(f"{base}/v2/connectors", headers=headers)
    said = response.text[:200]
    if response.status_code == 401:
        return _result(REFUSED, f"TextQL refused this key (401: {said})")
    if response.status_code != 200:
        # 403 means this key may not LIST connections, which says nothing about asking.
        return _result(UNREACHABLE, f"TextQL answered {response.status_code}, which says nothing about the key: {said}")
    try:
        listed = response.json()
    except ValueError:
        listed = None
    if not isinstance(listed, list):
        return _result(UNREACHABLE, f"TextQL listed its connections in a shape this check does not know: {said}")
    seen = {item.get("id") for item in listed if isinstance(item, dict)}
    absent = [str(c) for c in connector_ids(values.get("TEXTQL_CONNECTOR_IDS")) if c not in seen]
    if absent:
        return _result(UNREACHABLE, f"connection {', '.join(absent)} is not listed for this key")
    return _result(OK, "TextQL took this key and its data connections")


def _without_values(text: str, values: Mapping[str, str]) -> str:
    """As agent_kit.login.without_values: no value checked, in any shape."""
    whole = [v.strip() for v in values.values() if isinstance(v, str) and len(v.strip()) >= 4]
    pieces = set(whole)
    for value in whole:
        pieces.update(line.strip() for line in value.splitlines() if len(line.strip()) >= 16)
    encoded = {base64.b64encode(v.encode()).decode() for v in whole}
    encoded |= {base64.b64encode(f"{a}:{b}".encode()).decode() for a in whole for b in whole if a != b}
    for piece in sorted(pieces | encoded, key=len, reverse=True):
        text = text.replace(piece, "[redacted]")
    return text


def _run_check(check: Callable[[Mapping[str, str]], dict], values: Mapping[str, str]) -> dict[str, str]:
    try:
        answer = check(values)
    except httpx.HTTPError as error:
        state, detail = UNREACHABLE, f"could not reach TextQL: {type(error).__name__}: {error}"
    except Exception as error:  # noqa: BLE001 - a broken check must not turn the agent off
        state, detail = UNREACHABLE, f"the check failed: {type(error).__name__}: {error}"
    else:
        if isinstance(answer, dict) and answer.get("state") in STATES:
            state, detail = answer["state"], str(answer.get("detail") or "")
        else:
            state, detail = UNREACHABLE, f"the check gave an answer this service does not know: {answer!r}"
    return _result(state, _without_values(detail, values))


def build_handler(ask: Callable[[str], TextQLAnswer] | None,
                  check: Callable[[Mapping[str, str]], dict] | None = None) -> type[BaseHTTPRequestHandler]:
    """`ask` is None when TEXTQL_API_KEY is missing: the service then says so.
    Without `check` there is no POST /check, as in every image before it existed."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._send(404, {"error": f"no route {self.path}"})
            elif ask is None:
                self._send(503, {"ok": False, "error": "TEXTQL_API_KEY is not set"})
            else:
                self._send(200, {"ok": True})

        def _check(self) -> None:
            try:
                length = int(self.headers.get("content-length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY_BYTES:
                self._send(413 if length > MAX_BODY_BYTES else 400, {"error": "bad content-length"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self._send(400, {"error": "send a JSON object"})
                return
            typed = body.get("values")
            if typed is None:
                values, source = dict(os.environ), "saved"
            elif isinstance(typed, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in typed.items()):
                values, source = typed, "typed"
            else:
                self._send(400, {"error": "values must be an object of text"})
                return
            answer = _run_check(check, values)
            log("INFO", "login", "check", agent="textql", state=answer["state"], values=source)
            self._send(200, answer)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/check" and check is not None:
                self._check()
                return
            if self.path != "/ask":
                self._send(404, {"error": f"no route {self.path}"})
                return
            if ask is None:
                self._send(503, {"error": "TEXTQL_API_KEY is not set"})
                return
            try:
                length = int(self.headers.get("content-length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY_BYTES:
                # Refused unread: a negative length reads until the caller hangs up.
                self._send(413 if length > MAX_BODY_BYTES else 400, {"error": "bad content-length"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"error": "body must be JSON"})
                return
            question = body.get("question") if isinstance(body, dict) else None
            if not isinstance(question, str) or not question.strip():
                self._send(400, {"error": "question must be text"})
                return
            ids = {"request": self.headers.get("x-request-id") or None, "run": self.headers.get("x-run-id") or None}
            started = time.perf_counter()
            ms = lambda: round((time.perf_counter() - started) * 1000)  # noqa: E731
            try:
                answer = ask(question)
            except TextQLError as error:
                log("WARN", "textql", "ask failed", **ids, ms=ms(), error=redact(error))
                self._send(502, {"error": redact(error)})
                return
            except Exception as error:  # noqa: BLE001 - logged; the reply stays short
                log("ERROR", "textql", "ask failed", **ids, ms=ms(), error=f"{type(error).__name__}: {redact(error)}")
                self._send(500, {"error": f"{type(error).__name__}: {redact(error)}"})
                return
            log("INFO", "textql", "ask", **ids, ms=ms(), charts=len(answer.charts))
            # TextQL bills in its own credits and its reply carries no price.
            self._send(200, {"answer": answer.text, "costUsd": 0.0, "tokensIn": 0, "tokensOut": 0,
                             "charts": list(answer.charts)})

    return Handler


def main() -> int:
    key = (os.environ.get("TEXTQL_API_KEY") or "").strip()
    ask = None
    if key and "replace" not in key.lower():
        reader = TextQLReader(
            key,
            client=httpx.Client(timeout=TEXTQL_TIMEOUT_SECONDS),
            base_url=os.environ.get("TEXTQL_BASE_URL") or "https://app.textql.com",
            connector_ids=connector_ids(os.environ.get("TEXTQL_CONNECTOR_IDS")),
        )
        ask = reader.ask_detailed
    port = int(os.environ.get("PORT") or 8080)
    log("INFO" if ask else "WARN", "textql", "listening", port=port, state="ready" if ask else "no TEXTQL_API_KEY")
    ThreadingHTTPServer(("0.0.0.0", port), build_handler(ask, check_login)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
