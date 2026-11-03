from urllib.parse import parse_qs

import httpx
import pytest

from cliq_agent import server
from cliq_agent.server import check_login

LOGIN = {"ZOHO_DC": "eu", "ZOHO_CLIENT_ID": "1000.ID", "ZOHO_CLIENT_SECRET": "s3cret", "ZOHO_REFRESH_TOKEN": "1000.refresh"}


def zoho(status, body=None, text=None):
    seen = []

    def handler(request):
        seen.append(request)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_refreshes_the_token_once_in_the_accounts_region():
    client, seen = zoho(200, {"access_token": "1000.access", "expires_in": 3600})
    assert check_login(LOGIN, client)["state"] == "ok"
    assert [(r.method, str(r.url)) for r in seen] == [("POST", "https://accounts.zoho.eu/oauth/v2/token")]
    form = parse_qs(seen[0].content.decode())
    assert form["grant_type"] == ["refresh_token"] and form["client_id"] == ["1000.ID"]


@pytest.mark.parametrize("error", ["invalid_code", "invalid_client", "invalid_client_secret",
                                   "unauthorized_client", "invalid_grant"])
def test_a_refused_grant_is_refused(error):
    client, _ = zoho(200, {"error": error})
    answer = check_login(LOGIN, client)
    assert answer["state"] == "refused" and error in answer["detail"]


def test_too_many_requests_is_not_a_refusal():
    client, _ = zoho(400, {"error": "Access Denied",
                           "error_description": "You have made too many requests continuously."})
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_reply_that_is_not_json_is_not_a_refusal():
    client, _ = zoho(502, text="Bad gateway")
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_missing_login_is_refused_without_asking():
    client, seen = zoho(200, {})
    answer = check_login({**LOGIN, "ZOHO_REFRESH_TOKEN": ""}, client)
    assert answer["state"] == "refused" and "ZOHO_REFRESH_TOKEN" in answer["detail"]
    assert seen == []


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
