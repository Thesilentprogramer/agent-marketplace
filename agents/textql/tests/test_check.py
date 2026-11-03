import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import httpx
import pytest

from textql_agent import server
from textql_agent.server import build_handler, check_login

LOGIN = {"TEXTQL_API_KEY": "tql-key-1", "TEXTQL_CONNECTOR_IDS": "70, 630"}


def textql(status, body=None, text=None):
    seen = []

    def handler(request):
        seen.append(request)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_check_lists_the_connections_with_the_key():
    client, seen = textql(200, [{"id": 70, "name": "Sales", "type": "postgres"}, {"id": 630, "name": "Ops", "type": "bq"}])
    assert check_login(LOGIN, client)["state"] == "ok"
    assert [str(r.url) for r in seen] == ["https://app.textql.com/v2/connectors"]
    assert seen[0].headers["authorization"] == "Bearer tql-key-1"


def test_a_connection_missing_from_the_list_is_not_checked_yet_never_refused():
    client, _ = textql(200, [{"id": 70, "name": "Sales", "type": "postgres"}])
    answer = check_login(LOGIN, client)
    assert answer == {"state": "unreachable", "detail": "connection 630 is not listed for this key"}


def test_a_bad_key_is_refused():
    client, _ = textql(401, {"error": {"code": "unauthenticated", "message": "Authentication required"}})
    assert check_login(LOGIN, client)["state"] == "refused"


@pytest.mark.parametrize("status", [403, 429, 500])
def test_a_key_that_may_not_list_or_a_busy_textql_is_not_a_refusal(status):
    client, _ = textql(status, {"error": {"code": "x", "message": "y"}})
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_list_in_another_shape_is_not_a_refusal():
    client, _ = textql(200, {"connectors": []})
    assert check_login(LOGIN, client)["state"] == "unreachable"


def test_a_missing_key_is_refused_without_asking():
    client, seen = textql(200, [])
    assert check_login({**LOGIN, "TEXTQL_API_KEY": ""}, client)["state"] == "refused"
    assert seen == []


@pytest.fixture
def serve():
    servers = []

    def start(check):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(None, check))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def post(base, body):
    request = urllib.request.Request(base + "/check", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_the_route_checks_the_values_it_was_sent_and_logs_none(serve, capsys):
    seen = []

    def check(values):
        seen.append(dict(values))
        return {"state": "refused", "detail": "TextQL refused this key"}

    assert post(serve(check), {"values": {"TEXTQL_API_KEY": "s3cr3t-value"}}) == (
        200, {"state": "refused", "detail": "TextQL refused this key"})
    assert seen == [{"TEXTQL_API_KEY": "s3cr3t-value"}]
    out = capsys.readouterr()
    assert "s3cr3t-value" not in out.out + out.err and "values=typed" in out.out + out.err


def test_without_a_check_there_is_no_route(serve):
    assert post(serve(None), {})[0] == 404


def test_values_must_be_an_object_of_text(serve):
    base = serve(lambda values: {"state": "ok"})
    assert post(base, {"values": ["x"]})[0] == 400


def test_a_check_that_breaks_is_unreachable(serve):
    assert post(serve(lambda values: {}["missing"]), {})[1]["state"] == "unreachable"


def test_main_serves_the_check(monkeypatch):
    got = {}

    class Server:
        def __init__(self, address, handler):
            pass

        def serve_forever(self):
            pass

    monkeypatch.setattr(server, "build_handler", lambda ask, check=None: got.update(check=check))
    monkeypatch.setattr(server, "ThreadingHTTPServer", Server)
    server.main()
    assert got["check"] is check_login


def test_the_route_never_sends_back_a_value_it_checked(serve):
    def check(values):
        return {"state": "refused", "detail": f"TextQL said no to {values['TEXTQL_API_KEY']}"}

    code, answer = post(serve(check), {"values": {"TEXTQL_API_KEY": "tql\nkey-with-a-line-break"}})
    assert code == 200 and "key-with-a-line-break" not in answer["detail"] and "tql" not in answer["detail"]


def test_a_401_body_quoting_the_key_past_200_characters_does_not_leak_it():
    key = "tql-key-0123456789-abcdefghij"
    client, _ = textql(401, text="y" * 195 + key)
    answer = server._run_check(lambda values: check_login(values, client), {"TEXTQL_API_KEY": key})
    assert answer["state"] == "refused" and "tql-k" not in answer["detail"] and "abcdefghij" not in answer["detail"]
