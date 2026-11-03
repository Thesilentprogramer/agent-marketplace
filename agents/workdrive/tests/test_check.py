from urllib.parse import parse_qs

import httpx
import pytest

from workdrive_agent import server
from workdrive_agent.server import check_login

LOGIN = {"WORKDRIVE_MCP_URL": "https://workdrive.zoho.example/mcp/message",
         "WORKDRIVE_CLIENT_ID": "1000.ID", "WORKDRIVE_REFRESH_TOKEN": "1000.refresh"}
METADATA = {"token_endpoint": "https://accounts.zoho.example/oauth/v2/token"}


def zoho(metadata=(200, METADATA), token=(200, {"access_token": "1000.access"})):
    seen = []

    def handler(request):
        seen.append(request)
        status, body = metadata if request.url.path.startswith("/.well-known/") else token
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_finds_the_token_address_then_refreshes_once():
    client, seen = zoho()
    assert check_login(LOGIN, client)["state"] == "ok"
    assert [(r.method, str(r.url)) for r in seen] == [
        ("GET", "https://workdrive.zoho.example/.well-known/oauth-authorization-server"),
        ("POST", "https://accounts.zoho.example/oauth/v2/token")]
    form = parse_qs(seen[1].content.decode())
    assert form == {"grant_type": ["refresh_token"], "refresh_token": ["1000.refresh"], "client_id": ["1000.ID"]}


@pytest.mark.parametrize("error", ["invalid_code", "invalid_client"])
def test_a_refused_grant_is_refused(error):
    client, _ = zoho(token=(200, {"error": error}))
    answer = check_login(LOGIN, client)
    assert answer["state"] == "refused" and error in answer["detail"]


def test_a_server_without_its_oauth_metadata_is_not_a_refusal():
    client, _ = zoho(metadata=(404, {}))
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_too_many_requests_is_not_a_refusal():
    client, _ = zoho(token=(400, {"error": "Access Denied"}))
    assert check_login(LOGIN, client)["state"] == "unreachable"


@pytest.mark.parametrize("url", ["http://workdrive.zoho.example/mcp", "workdrive", "https://"])
def test_an_address_that_cannot_be_the_server_is_refused_without_asking(url):
    client, seen = zoho()
    answer = check_login({**LOGIN, "WORKDRIVE_MCP_URL": url}, client)
    assert answer["state"] == "refused" and "WORKDRIVE_MCP_URL" in answer["detail"]
    assert seen == []


def test_a_missing_login_is_refused_without_asking():
    client, seen = zoho()
    answer = check_login({**LOGIN, "WORKDRIVE_REFRESH_TOKEN": ""}, client)
    assert answer["state"] == "refused" and "WORKDRIVE_REFRESH_TOKEN" in answer["detail"]
    assert seen == []


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
