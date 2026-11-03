import base64

import httpx

from jira_agent import server
from jira_agent.server import check_login

LOGIN = {"JIRA_DOMAIN": "acme", "JIRA_EMAIL": "ops@acme.example", "JIRA_API_TOKEN": "tok-1"}


def jira(status, text="{}"):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, text=text)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_asks_jira_who_the_login_is():
    client, seen = jira(200, '{"accountId": "a1"}')
    assert check_login(LOGIN, client)["state"] == "ok"
    assert [str(r.url) for r in seen] == ["https://acme.atlassian.net/rest/api/3/myself"]
    assert seen[0].headers["authorization"] == "Basic " + base64.b64encode(b"ops@acme.example:tok-1").decode()


def test_a_bad_token_is_refused():
    client, _ = jira(401)
    assert check_login(LOGIN, client)["state"] == "refused"


def test_a_site_that_does_not_exist_is_refused_and_named():
    client, _ = jira(404)
    answer = check_login(LOGIN, client)
    assert answer["state"] == "refused" and "acme.atlassian.net" in answer["detail"]


def test_a_busy_jira_is_not_a_refusal():
    client, _ = jira(429)
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_missing_token_is_refused_without_asking():
    client, seen = jira(200)
    answer = check_login({**LOGIN, "JIRA_API_TOKEN": ""}, client)
    assert answer["state"] == "refused" and "JIRA_API_TOKEN" in answer["detail"]
    assert seen == []


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
