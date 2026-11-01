"""Zoho Cliq as its own MCP server (catalog kind "mcp").

The tools are the router's Cliq tools; the router's model still drives them,
over MCP. Settings come from the environment the client's settings service
starts this with: ZOHO_DC (the region) from the form, and ZOHO_CLIENT_ID,
ZOHO_CLIENT_SECRET and ZOHO_REFRESH_TOKEN, which the Zoho sign-in covers.

  python -m cliq_agent.server
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx

from agent_kit import login
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from cliq_agent.zoho_cliq import CliqReader, make_cliq_tools

KEYS = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
# Zoho's token errors that mean the login itself is no good. Anything else,
# such as "Access Denied" for too many requests, says nothing about it.
REFUSALS = frozenset({"invalid_code", "invalid_client", "invalid_client_secret", "unauthorized_client", "invalid_grant"})
HTTP_TIMEOUT_SECONDS = 30.0


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None) -> tuple[list, str | None]:
    """The tools, or none and why."""
    problem = missing(env, KEYS)
    if problem:
        return [], problem
    reader = CliqReader(
        dc=(env.get("ZOHO_DC") or "com").strip().lstrip("."),
        client_id=credential(env, "ZOHO_CLIENT_ID"),
        client_secret=credential(env, "ZOHO_CLIENT_SECRET"),
        refresh_token=credential(env, "ZOHO_REFRESH_TOKEN"),
        client=client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS),
    )
    return list(make_cliq_tools(reader)), None


def check_login(values: Mapping[str, str], client: httpx.Client | None = None) -> dict[str, str]:
    """One refresh of the access token, at the reader's own Zoho address."""
    problem = missing(values, KEYS)
    if problem:
        return login.result(login.REFUSED, problem)
    with login.http(client) as http:
        reader = CliqReader(
            dc=(values.get("ZOHO_DC") or "com").strip().lstrip("."),
            client_id=credential(values, "ZOHO_CLIENT_ID"),
            client_secret=credential(values, "ZOHO_CLIENT_SECRET"),
            refresh_token=credential(values, "ZOHO_REFRESH_TOKEN"),
            client=http,
        )
        # The form CliqReader._access_token sends.
        response = http.post(f"{reader.accounts_base}/oauth/v2/token", data={
            "grant_type": "refresh_token",
            "client_id": reader.client_id,
            "client_secret": reader.client_secret,
            "refresh_token": reader.refresh_token,
        })
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return login.from_status("Zoho", response, refused=())
    if body.get("access_token"):
        return login.result(login.OK, "Zoho took this login")
    error = str(body.get("error") or "")
    if error in REFUSALS:
        return login.result(login.REFUSED, f"Zoho refused this login ({error})")
    return login.result(login.UNREACHABLE, f"Zoho answered {response.status_code} {error or response.text[:200]}, "
                                           "which says nothing about the login")


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="cliq", check=check_login)


if __name__ == "__main__":
    main()
