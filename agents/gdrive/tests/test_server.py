import json
import os
import stat
from pathlib import Path

from gdrive_agent.server import build_tools, key_path

KEY = '{"type": "service_account", "client_email": "reader@example.invalid"}'


CATALOG = json.loads((Path(__file__).resolve().parents[1] / "catalog-1.0.0.json").read_text(encoding="utf-8"))


def test_the_server_offers_exactly_the_tools_its_catalog_entry_names(tmp_path):
    tools, problem = build_tools({"GOOGLE_SA_JSON": KEY, "CACHE_DIR": str(tmp_path)}, key_dir=tmp_path)
    assert problem is None
    assert sorted(t.name for t in tools) == sorted(CATALOG["router"]["agent"]["tools"])


def test_the_catalog_describes_each_tool_as_the_tool_describes_itself(tmp_path):
    tools, _ = build_tools({"GOOGLE_SA_JSON": KEY, "CACHE_DIR": str(tmp_path)}, key_dir=tmp_path)
    described = CATALOG["router"]["tool_descriptions"]
    assert {t.name: " ".join(t.description.split()) for t in tools} == {
        name: " ".join(text.split()) for name, text in described.items()}


def test_the_key_can_arrive_as_its_contents_and_is_kept_private(tmp_path):
    path = key_path(KEY, tmp_path)
    assert Path(path).read_text(encoding="utf-8") == KEY
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_key_can_still_be_a_path(tmp_path):
    assert key_path("/run/keys/sa.json", tmp_path) == "/run/keys/sa.json"


def test_without_its_key_it_offers_nothing_and_says_why(tmp_path):
    assert build_tools({}, key_dir=tmp_path) == ([], "GOOGLE_SA_JSON is not set")


def test_the_google_token_is_minted_once_and_reused_until_it_expires(tmp_path, monkeypatch):
    """Review finding: minting a token on every call cost two extra round trips
    per file read. Tokens last an hour."""
    from google.oauth2 import service_account

    from gdrive_agent.server import service_account_token_provider

    made = []

    class FakeCredentials:
        def __init__(self):
            self.valid, self.token, self.refreshes = False, None, 0

        def refresh(self, request):
            self.refreshes += 1
            self.valid, self.token = True, f"token-{self.refreshes}"

    def from_info(info, scopes):
        made.append(FakeCredentials())
        return made[-1]

    monkeypatch.setattr(service_account.Credentials, "from_service_account_info", staticmethod(from_info))
    key = tmp_path / "key.json"
    key.write_text("{}")
    provide = service_account_token_provider(str(key), ("scope",))

    assert [provide(), provide()] == ["token-1", "token-1"]
    made[0].valid = False  # expired
    assert provide() == "token-2"
    assert len(made) == 1
