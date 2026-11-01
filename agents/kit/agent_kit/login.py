"""Whether a vendor takes an agent's login: the answer to POST /check.

A check makes ONE cheap request to the vendor (each agent's server.py says
which) and answers {"state": ..., "detail": ...}:

  ok           the vendor answered and took the login
  refused      the vendor answered and refused it, or the values cannot work
  unreachable  no answer, or one that says nothing about the login

Only a refusal the agent recognises is "refused": the settings service turns
an agent off when its login is refused, so anything unforeseen -- a timeout, a
429, a 5xx, a reply in a shape nobody expected, a check that crashed -- is
"unreachable", which the page shows as "not checked".
"""

from __future__ import annotations

import base64
import contextlib
from collections.abc import Callable, Collection, Iterator, Mapping

import httpx

from agent_kit.log import redact

OK = "ok"
REFUSED = "refused"
UNREACHABLE = "unreachable"
STATES = (OK, REFUSED, UNREACHABLE)
CHECK_TIMEOUT_SECONDS = 15.0
DETAIL_CHARS = 300


def result(state: str, detail: str = "") -> dict[str, str]:
    """A check's answer. The detail is cleaned only in run(): values first, then
    redact() and the length cut, so no cut or rewrite can leave part of a value."""
    return {"state": state, "detail": detail}


def from_status(vendor: str, response: httpx.Response, refused: Collection[int] = (401, 403)) -> dict[str, str]:
    """A vendor's answer read conservatively: 2xx took the login, a status in
    `refused` refused it, anything else says nothing about it."""
    status = response.status_code
    said = response.text
    if 200 <= status < 300:
        return result(OK, f"{vendor} took this login")
    if status in refused:
        return result(REFUSED, f"{vendor} refused this login ({status}: {said})")
    return result(UNREACHABLE, f"{vendor} answered {status}, which says nothing about the login: {said}")


@contextlib.contextmanager
def http(client: httpx.Client | None) -> Iterator[httpx.Client]:
    """The caller's client (tests pass one), or a new one closed afterwards."""
    if client is not None:
        yield client
        return
    with httpx.Client(timeout=CHECK_TIMEOUT_SECONDS) as own:
        yield own


def without_values(text: str, values: Mapping[str, str]) -> str:
    """`text` with every value it was checked with taken out: each value of 4 or
    more characters, each long line of a many-line one (a key file), and their
    Basic-auth encodings, alone and in pairs ("email:token"). A vendor's error
    can quote what it was sent, in any shape redact() does not know."""
    whole = [v.strip() for v in values.values() if isinstance(v, str) and len(v.strip()) >= 4]
    pieces = set(whole)
    for value in whole:
        pieces.update(line.strip() for line in value.splitlines() if len(line.strip()) >= 16)
    encoded = {base64.b64encode(v.encode()).decode() for v in whole}
    encoded |= {base64.b64encode(f"{a}:{b}".encode()).decode() for a in whole for b in whole if a != b}
    for piece in sorted(pieces | encoded, key=len, reverse=True):
        text = text.replace(piece, "[redacted]")
    return text


def run(check: Callable[[Mapping[str, str]], dict], values: Mapping[str, str]) -> dict[str, str]:
    """`check(values)`, never raising: whatever goes wrong is "unreachable". The
    detail never carries a value it was checked with (without_values)."""
    try:
        answer = check(values)
    except httpx.HTTPError as error:
        state, detail = UNREACHABLE, f"could not reach the vendor: {type(error).__name__}: {error}"
    except Exception as error:  # noqa: BLE001 - a broken check must not turn an agent off
        state, detail = UNREACHABLE, f"the check failed: {type(error).__name__}: {error}"
    else:
        if isinstance(answer, dict) and answer.get("state") in STATES:
            state, detail = answer["state"], str(answer.get("detail") or "")
        else:
            state, detail = UNREACHABLE, f"the check gave an answer this kit does not know: {answer!r}"
    return result(state, redact(without_values(detail, values), DETAIL_CHARS))
