import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import httpx
import pytest

from agent_kit import login
from agent_kit.mcp_server import build_handler


@pytest.fixture
def serve():
    servers = []

    def start(check=None):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), build_handler([], None, "acme", check=check))
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


def answering(status, headers=None, text="{}"):
    return httpx.Response(status, headers=headers or {}, text=text,
                          request=httpx.Request("GET", "https://vendor.example/check"))


def test_check_answers_with_the_values_it_was_sent(serve):
    seen = []

    def check(values):
        seen.append(dict(values))
        return login.result(login.OK, "Acme took this login")

    assert post(serve(check), {"values": {"ACME_TOKEN": "t-1"}}) == (200, {"state": "ok", "detail": "Acme took this login"})
    assert seen == [{"ACME_TOKEN": "t-1"}]


def test_check_without_values_uses_the_settings_it_was_started_with(serve, monkeypatch):
    monkeypatch.setenv("ACME_TOKEN", "from-the-environment")
    seen = []

    def check(values):
        seen.append(values.get("ACME_TOKEN"))
        return login.result(login.OK)

    assert post(serve(check), {})[0] == 200
    assert seen == ["from-the-environment"]


def test_an_agent_without_a_check_has_no_route(serve):
    assert post(serve(None), {})[0] == 404


def test_values_must_be_an_object_of_text(serve):
    base = serve(lambda values: login.result(login.OK))
    assert post(base, {"values": ["x"]})[0] == 400
    assert post(base, {"values": {"A": 1}})[0] == 400


def test_a_vendor_that_cannot_be_reached_is_unreachable_never_refused():
    def check(values):
        raise httpx.ConnectError("no route to host")

    assert login.run(check, {})["state"] == "unreachable"


def test_a_check_that_breaks_or_answers_nonsense_is_unreachable():
    assert login.run(lambda values: {}["missing"], {})["state"] == "unreachable"
    assert login.run(lambda values: {"state": "maybe"}, {})["state"] == "unreachable"


@pytest.mark.parametrize("status,state", [(200, "ok"), (204, "ok"), (401, "refused"), (403, "refused"),
                                          (404, "unreachable"), (408, "unreachable"), (429, "unreachable"),
                                          (500, "unreachable"), (503, "unreachable")])
def test_a_vendors_status_is_read_conservatively(status, state):
    assert login.from_status("Acme", answering(status))["state"] == state


def test_an_agent_may_name_its_own_refusals():
    assert login.from_status("Acme", answering(404), refused=(401, 404))["state"] == "refused"


def test_the_detail_carries_no_token_and_is_short():
    detail = login.run(lambda values: login.from_status("Acme", answering(401, text="bad: Bearer ghp_abcdefghijklmnop " + "x" * 900)),
                       {})["detail"]
    assert "ghp_abcdefghijklmnop" not in detail and len(detail) <= 301


def test_the_check_logs_no_value(serve, capsys):
    post(serve(lambda values: login.result(login.REFUSED, "Acme refused this login")),
         {"values": {"ACME_TOKEN": "s3cr3t-value"}})
    out = capsys.readouterr()
    assert "s3cr3t-value" not in out.out + out.err
    assert "state=refused" in out.out + out.err and "values=typed" in out.out + out.err


def test_the_detail_never_carries_a_value_it_was_checked_with_in_any_shape():
    import base64

    token = "tok-1\nsecond-line-of-the-key-xyz"
    said = (f"refused {token} and {base64.b64encode(b'ops@acme.example:' + token.encode()).decode()} "
            f"and only second-line-of-the-key-xyz")
    answer = login.run(lambda values: login.result(login.REFUSED, said),
                       {"JIRA_EMAIL": "ops@acme.example", "JIRA_API_TOKEN": token, "PORT": "80"})
    assert answer["state"] == "refused"
    assert "tok-1" not in answer["detail"] and "second-line-of-the-key" not in answer["detail"]
    assert "b3BzQGFjbWUuZXhhbXBsZT" not in answer["detail"]


def test_a_value_the_vendor_quotes_across_the_old_cut_is_still_taken_out():
    token = "ATATT3xFfGF0-secret-token-0123456789"
    said = "x" * 190 + token

    def check(values):
        return login.from_status("Jira", answering(401, text=said))

    answer = login.run(check, {"JIRA_API_TOKEN": token})
    assert answer["state"] == "refused" and "ATATT3" not in answer["detail"] and "secret-token" not in answer["detail"]


def test_a_value_redact_would_alter_is_taken_out_before_redact_runs():
    url = "https://workdrive.example/mcp/SECRETPATHKEY123/message?k=1"
    answer = login.run(lambda values: login.result(login.UNREACHABLE, f"could not reach {url}"),
                       {"WORKDRIVE_MCP_URL": url})
    assert "SECRETPATHKEY123" not in answer["detail"]
