import httpx

from agent_kit.cache import DiskCache
from google_fake import FakeGoogle, xlsx
from gdrive_agent.drive import DriveIndex
from gdrive_agent.files import FileReader
from gdrive_agent.kinds import FOLDER, SHEET
from gdrive_agent.tools import make_drive_tools


def tools(fake: FakeGoogle, tmp_path) -> dict:
    index = DriveIndex(client=httpx.Client(transport=httpx.MockTransport(fake.handler)), token_provider=lambda: "tok")
    made = make_drive_tools(index, FileReader(index, DiskCache(tmp_path / "gdrive")))
    return {t.name: t.func for t in made}  # .func: the tuple a content_and_artifact tool returns


def test_a_listing_names_each_files_kind_and_marks_what_cannot_be_read(tmp_path):
    fake = FakeGoogle()
    fake.add("v1", "demo.mp4", "video/mp4")
    fake.add("s1", "Budget", SHEET)
    fake.add("f1", "Finance", FOLDER)
    fake.list_result = ["v1", "s1", "f1"]
    text, rows = tools(fake, tmp_path)["browse_drive"]()
    lines = text.splitlines()
    assert lines[0].startswith("FOLDER\tf1\tFinance\t")
    assert lines[1].startswith("FILE\ts1\tBudget\tGoogle Sheet\t(modified 2026-10-01)\t")
    assert lines[2].startswith("FILE\tv1\tdemo.mp4\tvideo, cannot be read\t")
    assert rows["columns"] == ["name", "id", "kind", "modified"]
    assert [r[2] for r in rows["rows"]] == ["folder", "Google Sheet", "video, cannot be read"]


def test_an_empty_search_says_what_was_searched_in_the_routers_words(tmp_path):
    text, rows = tools(FakeGoogle(), tmp_path)["search_drive"]("pricing")
    assert text == "no matches for: 'pricing' in the files shared with this account"
    assert rows["rows"] == []


def test_reading_a_sheet_gives_its_link_text_and_rows(tmp_path):
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, content=xlsx({"Sheet1": [["Quarter", "Revenue"], ["Q3", "48200"]]}))
    text, rows = tools(fake, tmp_path)["read_drive_file"]("s1")
    assert text.splitlines()[0] == "=== Budget (Google Sheet) === https://drive.google.com/file/d/s1/view"
    assert rows["columns"] == ["Quarter", "Revenue"] and rows["rows"] == [["Q3", "48200"]]


def test_a_file_that_cannot_be_read_says_so_and_forbids_guessing(tmp_path):
    fake = FakeGoogle()
    fake.add("v1", "demo.mp4", "video/mp4")
    text, rows = tools(fake, tmp_path)["read_drive_file"]("v1")
    assert text.startswith("cannot be read: demo.mp4 (video)") and "never guess" in text
    assert rows["rows"] == []


def test_a_google_refusal_comes_back_as_text_not_a_crash(tmp_path):
    text, rows = tools(FakeGoogle(), tmp_path)["read_drive_file"]("missing")
    assert text.startswith("google drive error: no file with id missing")
    assert rows["rows"] == []
