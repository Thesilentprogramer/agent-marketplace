"""Zoho WorkDrive as its own MCP server (catalog kind "mcp").

The tools are the router's WorkDrive tools, unchanged; the router's model still
drives them, over MCP. They in turn reach Zoho's own WorkDrive MCP server, and
read file contents through Zoho's download API, as they did in the router.
Settings come from the environment the client's settings service starts this
with: WORKDRIVE_MCP_URL from the form, and WORKDRIVE_CLIENT_ID and
WORKDRIVE_REFRESH_TOKEN, which the Zoho sign-in covers.

  python -m workdrive_agent.server
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx

from agent_kit import login
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from workdrive_agent.mcp import MCPClient, MCPError, discover_token_endpoint, refresh_token_provider
from workdrive_agent.workdrive import WorkDriveReader, make_workdrive_tools
from workdrive_agent.workdrive_direct import WorkDriveDirect

KEYS = ("WORKDRIVE_MCP_URL", "WORKDRIVE_CLIENT_ID", "WORKDRIVE_REFRESH_TOKEN")
# Zoho's token errors that mean the login itself is no good (as the Cliq agent's).
REFUSALS = frozenset({"invalid_code", "invalid_client", "invalid_client_secret", "unauthorized_client", "invalid_grant"})
HTTP_TIMEOUT_SECONDS = 30.0


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None) -> tuple[list, str | None]:
    """The tools, or none and why. Wired as the router's workdrive_tools wires them."""
    problem = missing(env, KEYS)
    if problem:
        return [], problem
    url = credential(env, "WORKDRIVE_MCP_URL")
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    token = refresh_token_provider(url, credential(env, "WORKDRIVE_CLIENT_ID"),
                                   credential(env, "WORKDRIVE_REFRESH_TOKEN"), client)
    reader = WorkDriveReader(MCPClient(url=url, token=token, client=client))
    content = None
    if (env.get("WORKDRIVE_DIRECT_API") or "true").strip().lower() not in ("false", "0", "no"):
        # The download host is named by the token response, so it is read lazily.
        def api_domain() -> str:
            token()
            return getattr(token, "api_domain", lambda: "")() or "https://www.zohoapis.com"

        content = WorkDriveDirect(api_domain=api_domain, token=token, client=client)
    return list(make_workdrive_tools(reader, content)), None


def check_login(values: Mapping[str, str], client: httpx.Client | None = None) -> dict[str, str]:
    """Find the token endpoint as the tools do, then one refresh of the token."""
    problem = missing(values, KEYS)
    if problem:
        return login.result(login.REFUSED, problem)
    url = credential(values, "WORKDRIVE_MCP_URL")
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        parsed = None
    if parsed is None or parsed.scheme != "https" or not parsed.host:
        return login.result(login.REFUSED, "WORKDRIVE_MCP_URL is not an address")
    with login.http(client) as http:
        try:
            endpoint = discover_token_endpoint(url, http)
        except MCPError as error:
            return login.result(login.UNREACHABLE, f"could not find WorkDrive's token address: {error}")
        # The form refresh_token_provider sends: a public client, so no secret.
        response = http.post(endpoint, data={
            "grant_type": "refresh_token",
            "refresh_token": credential(values, "WORKDRIVE_REFRESH_TOKEN"),
            "client_id": credential(values, "WORKDRIVE_CLIENT_ID"),
        })
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return login.from_status("Zoho", response, refused=())
    if body.get("access_token"):
        return login.result(login.OK, "Zoho took this login for WorkDrive")
    error = str(body.get("error") or "")
    if error in REFUSALS:
        return login.result(login.REFUSED, f"Zoho refused this login ({error})")
    return login.result(login.UNREACHABLE, f"Zoho answered {response.status_code} {error or response.text}, "
                                           "which says nothing about the login")


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="workdrive", check=check_login)


if __name__ == "__main__":
    main()
