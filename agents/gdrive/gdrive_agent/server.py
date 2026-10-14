"""Google Drive as its own MCP server (catalog kind "mcp", agent id gdrive).

GOOGLE_SA_JSON is the service account's key: the client's settings service
passes the key file's CONTENTS (a path on that server means nothing in here),
which are written to a private file for Google's library. A path still works,
for running this by hand.

  python -m gdrive_agent.server
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import httpx

from agent_kit.cache import DiskCache
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from gdrive_agent.drive import DRIVE_SCOPE, DriveIndex
from gdrive_agent.files import FileReader
from gdrive_agent.tools import make_drive_tools

HTTP_TIMEOUT_SECONDS = 30.0


def key_path(value: str, key_dir: Path | None = None) -> str:
    """A path to the key: the value itself, or a private file holding it."""
    if not value.lstrip().startswith("{"):
        return value
    handle, path = tempfile.mkstemp(prefix="sa-", suffix=".json", dir=key_dir)
    with os.fdopen(handle, "w", encoding="utf-8") as out:  # mkstemp makes it 0600
        out.write(value)
    return path


def service_account_token_provider(sa_json_path: str, scopes: Sequence[str]) -> Callable[[], str]:
    """Mint access tokens from a service-account key file for the given scopes."""

    # Built once and refreshed only when expired (tokens last an hour): minting a
    # new token on every call cost two extra round trips per file read.
    held: dict = {}

    def provide() -> str:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        credentials = held.get("credentials")
        if credentials is None:
            with open(sa_json_path, encoding="utf-8") as handle:
                info = json.load(handle)
            credentials = held["credentials"] = service_account.Credentials.from_service_account_info(
                info, scopes=list(scopes))
        if not credentials.valid:
            credentials.refresh(Request())
        return str(credentials.token)

    return provide


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None,
                key_dir: Path | None = None) -> tuple[list, str | None]:
    """The tools, or none and why."""
    problem = missing(env, ["GOOGLE_SA_JSON"])
    if problem:
        return [], problem
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    token_provider = service_account_token_provider(key_path(credential(env, "GOOGLE_SA_JSON"), key_dir),
                                                    (DRIVE_SCOPE,))
    index = DriveIndex(client=client, token_provider=token_provider)
    reader = FileReader(index, DiskCache(Path(env.get("CACHE_DIR") or ".cache") / "gdrive"))
    return list(make_drive_tools(index, reader)), None


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="gdrive")


if __name__ == "__main__":
    main()
