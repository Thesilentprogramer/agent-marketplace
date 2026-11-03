"""GitHub as its own MCP server (catalog kind "mcp").

The tools are the router's GitHub tools, unchanged; the router's model still
drives them, over MCP. Settings come from the environment the client's
settings service starts this with: GITHUB_REPO ("owner/name") and an optional
GITHUB_TOKEN (needed for a private repository and for code search).

  python -m github_agent.server
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import httpx

from agent_kit import login
from agent_kit.cache import DiskCache
from agent_kit.mcp_server import serve
from agent_kit.settings import credential
from github_agent.github import GitHubReader, make_github_tools

# The router's own default (router/app/config.py), so an unset repo means the same thing.
DEFAULT_REPO = "kaliperdev/langgraph-prototype"
HTTP_TIMEOUT_SECONDS = 30.0


def _repo(env: Mapping[str, str]) -> tuple[str, str | None]:
    """The repository to read, and why it cannot be read (or None)."""
    repo = (env.get("GITHUB_REPO") or "").strip() or DEFAULT_REPO
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        return repo, f"GITHUB_REPO must be 'owner/name', got {repo!r}"
    return repo, None


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None) -> tuple[list, str | None]:
    """The tools, or none and why."""
    repo, problem = _repo(env)
    if problem:
        return [], problem
    reader = GitHubReader(
        repo=repo,
        client=client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS),
        cache=DiskCache(Path(env.get("CACHE_DIR") or ".cache") / "github"),
        token=credential(env, "GITHUB_TOKEN"),
    )
    return list(make_github_tools(reader)), None


def check_login(values: Mapping[str, str], client: httpx.Client | None = None) -> dict[str, str]:
    """One read of the repository the agent reads, with the token when one is
    set: what it needs is that repository, so GET /user would prove less."""
    repo, problem = _repo(values)
    if problem:
        return login.result(login.REFUSED, problem)
    token = credential(values, "GITHUB_TOKEN")
    headers = {"accept": "application/vnd.github+json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    with login.http(client) as http:
        response = http.get(f"https://api.github.com/repos/{repo}", headers=headers)
    if response.status_code == 404:
        return login.result(login.REFUSED, f"GitHub has no repository {repo} that this token can see")
    # GitHub's primary limit says remaining 0; its secondary limit sends
    # retry-after, or says "rate limit" in the body. Neither is about the token.
    if response.status_code == 403 and (response.headers.get("x-ratelimit-remaining") == "0"
                                        or "retry-after" in response.headers
                                        or "rate limit" in response.text.lower()):
        return login.result(login.UNREACHABLE, "GitHub's rate limit is used up; try again later")
    if response.status_code == 200:
        return login.result(login.OK, f"GitHub took this login and can read {repo}")
    return login.from_status("GitHub", response, refused=(401, 403))


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="github", check=check_login)


if __name__ == "__main__":
    main()
