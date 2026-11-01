"""Google Docs as its own MCP server (catalog kind "mcp").

The tools are the router's Google Docs tools, unchanged; the router's model
still drives them, over MCP. GOOGLE_SA_JSON is the service account's key: the
client's settings service passes the key file's CONTENTS (a path on that server
means nothing in here), which are written to a private file for Google's
library. A path still works, for running this by hand.

  python -m gdocs_agent.server
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

import httpx

from agent_kit import login
from agent_kit.cache import DiskCache
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from gdocs_agent.drive import DRIVE_SCOPE, DriveIndex
from gdocs_agent.gdocs import DOCS_SCOPE, DocsReader, make_docs_tools, service_account_token_provider

SA_SCOPES = (DOCS_SCOPE, DRIVE_SCOPE)
HTTP_TIMEOUT_SECONDS = 30.0


def key_path(value: str, key_dir: Path | None = None) -> str:
    """A path to the key: the value itself, or a private file holding it."""
    if not value.lstrip().startswith("{"):
        return value
    handle, path = tempfile.mkstemp(prefix="sa-", suffix=".json", dir=key_dir)
    with os.fdopen(handle, "w", encoding="utf-8") as out:  # mkstemp makes it 0600
        out.write(value)
    return path


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None,
                key_dir: Path | None = None) -> tuple[list, str | None]:
    """The tools, or none and why. Wired as the router's gdocs_tools wires them."""
    problem = missing(env, ["GOOGLE_SA_JSON"])
    if problem:
        return [], problem
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    token_provider = service_account_token_provider(key_path(credential(env, "GOOGLE_SA_JSON"), key_dir), SA_SCOPES)
    index = DriveIndex(client=client, token_provider=token_provider)
    reader = DocsReader(client=client, token_provider=token_provider,
                        cache=DiskCache(Path(env.get("CACHE_DIR") or ".cache") / "gdocs"))
    return list(make_docs_tools(index, reader)), None


# Google's answers that mean the key itself is refused, wherever they appear in
# the error google-auth raises while minting a token.
REFUSALS = ("invalid_grant", "invalid_client", "unauthorized_client")
# Google's invalid_grant when this server's clock is off: the key may be fine.
WRONG_CLOCK = "Token must be a short-lived token"
# A 403 from Drive with one of these reasons is a limit, not a refusal.
LIMITS = frozenset({"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "quotaExceeded",
                    "RATE_LIMIT_EXCEEDED"})
ABOUT_URL = "https://www.googleapis.com/drive/v3/about"


def _reason(response: httpx.Response) -> str:
    try:
        errors = response.json()["error"]["errors"]
        return str(errors[0].get("reason") or "")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return ""


def check_login(values: Mapping[str, str], client: httpx.Client | None = None,
                key_dir: Path | None = None) -> dict[str, str]:
    """Mint a token from the key, then ask Drive whose it is: one token request
    and one Drive request. The private copy of the key is removed afterwards."""
    problem = missing(values, ["GOOGLE_SA_JSON"])
    if problem:
        return login.result(login.REFUSED, problem)
    value = credential(values, "GOOGLE_SA_JSON")
    if not value.lstrip().startswith("{") and not Path(value).is_file():
        return login.result(login.REFUSED, "GOOGLE_SA_JSON is not a service-account key")
    path = key_path(value, key_dir)
    try:
        try:
            token = service_account_token_provider(path, SA_SCOPES)()
        except Exception as error:  # noqa: BLE001 - sorted below; never raised out of a check
            said = f"{type(error).__name__}: {error}"
            if WRONG_CLOCK in said:
                return login.result(login.UNREACHABLE, f"Google doubts this server's clock, not the key: {said}")
            if any(code in said for code in REFUSALS):
                return login.result(login.REFUSED, f"Google refused this key ({said})")
            if isinstance(error, (ValueError, KeyError)):
                return login.result(login.REFUSED, f"GOOGLE_SA_JSON is not a service-account key ({said})")
            return login.result(login.UNREACHABLE, f"could not get a token from Google: {said}")
    finally:
        if path != value:
            Path(path).unlink(missing_ok=True)
    with login.http(client) as http:
        response = http.get(ABOUT_URL, params={"fields": "user"}, headers={"authorization": f"Bearer {token}"})
    if response.status_code == 200:
        email = ((response.json() or {}).get("user") or {}).get("emailAddress") or "the service account"
        return login.result(login.OK, f"Google took this key ({email})")
    if response.status_code == 403 and _reason(response) in LIMITS:
        return login.result(login.UNREACHABLE, f"Google's {_reason(response)} limit was hit; try again later")
    return login.from_status("Google", response, refused=(401, 403))


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="gdocs", check=check_login)


if __name__ == "__main__":
    main()
