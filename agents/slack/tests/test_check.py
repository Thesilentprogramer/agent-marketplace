import httpx
import pytest

from slack_agent import server
from slack_agent.server import check_login

LOGIN = {"SLACK_BOT_TOKEN": "xoxb-1-abc", "SLACK_USER_TOKEN": "xoxp-1-abc"}


def slack(*answers):
    """One (status, json body) per call, in order."""
    seen = []

    def handler(request):
        seen.append(request)
        status, body = answers[len(seen) - 1]
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_asks_slack_about_each_token_once():
    client, seen = slack((200, {"ok": True}), (200, {"ok": True}))
    assert check_login(LOGIN, client)["state"] == "ok"
    assert [(r.method, str(r.url)) for r in seen] == [("POST", "https://slack.com/api/auth.test")] * 2
    assert [r.headers["authorization"] for r in seen] == ["Bearer xoxb-1-abc", "Bearer xoxp-1-abc"]


def test_a_refused_bot_token_is_named_and_the_user_token_is_not_tried():
    client, seen = slack((200, {"ok": False, "error": "invalid_auth"}))
    answer = check_login(LOGIN, client)
    assert answer["state"] == "refused" and "the bot token" in answer["detail"]
    assert len(seen) == 1


def test_a_refused_user_token_is_named():
    client, _ = slack((200, {"ok": True}), (200, {"ok": False, "error": "token_revoked"}))
    answer = check_login(LOGIN, client)
    assert answer["state"] == "refused" and "the user token" in answer["detail"]


@pytest.mark.parametrize("status,body", [(429, {"ok": False, "error": "ratelimited"}),
                                         (200, {"ok": False, "error": "ratelimited"}),
                                         (200, {"ok": False, "error": "fatal_error"}),
                                         (503, {})])
def test_a_busy_or_puzzling_slack_is_not_a_refusal(status, body):
    client, _ = slack((status, body))
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_missing_token_is_refused_without_asking():
    client, seen = slack()
    answer = check_login({**LOGIN, "SLACK_USER_TOKEN": ""}, client)
    assert answer["state"] == "refused" and "SLACK_USER_TOKEN" in answer["detail"]
    assert seen == []


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
