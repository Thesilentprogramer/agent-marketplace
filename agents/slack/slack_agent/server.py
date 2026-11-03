"""Slack as its own MCP server (catalog kind "mcp").

The tools are the router's Slack tools, unchanged; the router's model still
drives them, over MCP. Logins come from the environment the client's settings
service starts this with: SLACK_BOT_TOKEN and SLACK_USER_TOKEN. No cache: Slack
reads always go live (see slack.py).

  python -m slack_agent.server
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx

from agent_kit import login
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from slack_agent.slack import SLACK_API, SlackReader, make_slack_tools

KEYS = ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN")
# Slack's answers that mean the token itself is no good (auth.test's error list).
REFUSALS = frozenset({"invalid_auth", "not_authed", "account_inactive", "token_revoked", "token_expired"})
HTTP_TIMEOUT_SECONDS = 30.0


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None) -> tuple[list, str | None]:
    """The tools, or none and why."""
    problem = missing(env, KEYS)
    if problem:
        return [], problem
    reader = SlackReader(
        bot_token=credential(env, "SLACK_BOT_TOKEN"),
        user_token=credential(env, "SLACK_USER_TOKEN"),
        client=client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS),
    )
    return list(make_slack_tools(reader)), None


def _token_problem(http: httpx.Client, which: str, token: str) -> dict[str, str] | None:
    """None when Slack takes this token; otherwise the check's answer."""
    response = http.post(f"{SLACK_API}/auth.test", headers={"authorization": f"Bearer {token}"})
    if response.status_code != 200:
        return login.from_status("Slack", response, refused=())
    body = response.json()
    if body.get("ok"):
        return None
    error = str(body.get("error") or "unknown error")
    if error in REFUSALS:
        return login.result(login.REFUSED, f"Slack refused {which} ({error})")
    return login.result(login.UNREACHABLE, f"Slack answered {error} for {which}, which says nothing about the login")


def check_login(values: Mapping[str, str], client: httpx.Client | None = None) -> dict[str, str]:
    """auth.test once per token, the bot's first; the first refusal ends it."""
    problem = missing(values, KEYS)
    if problem:
        return login.result(login.REFUSED, problem)
    with login.http(client) as http:
        for which, key in (("the bot token", "SLACK_BOT_TOKEN"), ("the user token", "SLACK_USER_TOKEN")):
            answer = _token_problem(http, which, credential(values, key))
            if answer is not None:
                return answer
    return login.result(login.OK, "Slack took the bot token and the user token")


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="slack", check=check_login)


if __name__ == "__main__":
    main()
