import httpx
import pytest

from github_agent import server
from github_agent.server import check_login


def github(status, headers=None, text="{}"):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers=headers or {}, text=text)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_reads_the_repository_with_the_token():
    client, seen = github(200)
    assert check_login({"GITHUB_REPO": "acme/app", "GITHUB_TOKEN": "ghp_x"}, client)["state"] == "ok"
    assert [str(r.url) for r in seen] == ["https://api.github.com/repos/acme/app"]
    assert seen[0].headers["authorization"] == "Bearer ghp_x"


def test_a_public_repository_needs_no_token():
    client, seen = github(200)
    assert check_login({"GITHUB_REPO": "acme/app"}, client)["state"] == "ok"
    assert "authorization" not in seen[0].headers


def test_a_bad_token_is_refused():
    client, _ = github(401, text='{"message": "Bad credentials"}')
    answer = check_login({"GITHUB_REPO": "acme/app", "GITHUB_TOKEN": "ghp_x"}, client)
    assert answer["state"] == "refused" and "GitHub refused" in answer["detail"]


def test_a_repository_the_token_cannot_see_is_refused_and_named():
    client, _ = github(404, text='{"message": "Not Found"}')
    answer = check_login({"GITHUB_REPO": "acme/app", "GITHUB_TOKEN": "ghp_x"}, client)
    assert answer["state"] == "refused" and "acme/app" in answer["detail"]


def test_running_out_of_requests_is_not_a_refusal():
    client, _ = github(403, headers={"x-ratelimit-remaining": "0"}, text='{"message": "API rate limit exceeded"}')
    assert check_login({"GITHUB_REPO": "acme/app"}, client)["state"] == "unreachable"


@pytest.mark.parametrize("headers,text", [
    ({"retry-after": "60", "x-ratelimit-remaining": "4000"}, '{"message": "Slow down"}'),
    ({"x-ratelimit-remaining": "4000"}, '{"message": "You have exceeded a secondary rate limit."}'),
])
def test_the_secondary_rate_limit_is_not_a_refusal(headers, text):
    client, _ = github(403, headers=headers, text=text)
    assert check_login({"GITHUB_REPO": "acme/app", "GITHUB_TOKEN": "ghp_x"}, client)["state"] == "unreachable"


def test_forbidden_for_another_reason_is_a_refusal():
    client, _ = github(403, headers={"x-ratelimit-remaining": "4999"}, text='{"message": "Resource not accessible"}')
    assert check_login({"GITHUB_REPO": "acme/app", "GITHUB_TOKEN": "ghp_x"}, client)["state"] == "refused"


def test_a_repository_that_is_not_owner_slash_name_is_refused_without_asking():
    client, seen = github(200)
    assert check_login({"GITHUB_REPO": "just-a-name"}, client)["state"] == "refused"
    assert seen == []


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
