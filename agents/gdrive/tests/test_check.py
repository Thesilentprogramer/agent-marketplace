import httpx
import pytest

from gdrive_agent import server
from gdrive_agent.server import check_login

KEY = '{"type": "service_account", "client_email": "reader@example.invalid"}'


def drive(status, body):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


class Minted:
    """The token step, without Google: what it was given, and what it does."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.outcome: str | Exception = "ya29.token"


@pytest.fixture
def minted(monkeypatch):
    state = Minted()

    def provider(path, scopes):
        def provide():
            with open(path, encoding="utf-8") as handle:
                state.calls.append({"path": path, "key": handle.read(), "scopes": tuple(scopes)})
            if isinstance(state.outcome, Exception):
                raise state.outcome
            return state.outcome

        return provide

    monkeypatch.setattr(server, "service_account_token_provider", provider)
    return state


def test_the_check_mints_a_token_and_asks_drive_whose_it_is(minted, tmp_path):
    client, seen = drive(200, {"user": {"emailAddress": "reader@example.invalid"}})
    answer = check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)
    assert answer["state"] == "ok" and "reader@example.invalid" in answer["detail"]
    assert [str(r.url) for r in seen] == ["https://www.googleapis.com/drive/v3/about?fields=user"]
    assert seen[0].headers["authorization"] == "Bearer ya29.token"
    assert minted.calls[0]["key"] == KEY


def test_the_private_copy_of_the_key_is_removed(minted, tmp_path):
    client, _ = drive(200, {"user": {}})
    check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)
    assert minted.calls and list(tmp_path.iterdir()) == []


def test_a_value_that_is_not_a_key_is_refused_without_asking_drive(minted, tmp_path):
    minted.outcome = ValueError("Service account info was not in the expected format")
    client, seen = drive(200, {})
    answer = check_login({"GOOGLE_SA_JSON": "{}"}, client, key_dir=tmp_path)
    assert answer["state"] == "refused" and "not a service-account key" in answer["detail"]
    assert seen == [] and list(tmp_path.iterdir()) == []


def test_text_that_is_neither_a_key_nor_a_key_file_is_refused(minted, tmp_path):
    client, seen = drive(200, {})
    assert check_login({"GOOGLE_SA_JSON": "not-a-key"}, client, key_dir=tmp_path)["state"] == "refused"
    assert minted.calls == [] and seen == []


def test_a_key_google_refuses_is_refused(minted, tmp_path):
    minted.outcome = RuntimeError("('invalid_grant: Invalid JWT Signature.', {'error': 'invalid_grant'})")
    client, _ = drive(200, {})
    assert check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)["state"] == "refused"


def test_a_wrong_clock_is_not_a_refusal(minted, tmp_path):
    minted.outcome = RuntimeError("('invalid_grant: Invalid JWT: Token must be a short-lived token (60 minutes)', {})")
    client, _ = drive(200, {})
    assert check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)["state"] == "unreachable"


def test_google_unreachable_while_minting_is_not_a_refusal(minted, tmp_path):
    minted.outcome = RuntimeError("TransportError: Connection aborted")
    client, _ = drive(200, {})
    assert check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)["state"] == "unreachable"


@pytest.mark.parametrize("status,body", [(401, {"error": {"errors": [{"reason": "authError"}]}}),
                                         (403, {"error": {"errors": [{"reason": "accessNotConfigured"}]}})])
def test_drive_refusing_the_token_is_refused(minted, tmp_path, status, body):
    client, _ = drive(status, body)
    assert check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)["state"] == "refused"


@pytest.mark.parametrize("status,body", [(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}),
                                         (403, {"error": {"errors": [{"reason": "RATE_LIMIT_EXCEEDED"}]}}),
                                         (429, {}), (500, {})])
def test_a_busy_drive_is_not_a_refusal(minted, tmp_path, status, body):
    client, _ = drive(status, body)
    assert check_login({"GOOGLE_SA_JSON": KEY}, client, key_dir=tmp_path)["state"] == "unreachable"


def test_main_serves_the_check(monkeypatch):
    got = {}
    monkeypatch.setattr(server, "serve", lambda *args, **kwargs: got.update(kwargs))
    server.main()
    assert got["check"] is check_login
