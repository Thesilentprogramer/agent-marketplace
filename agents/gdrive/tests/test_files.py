import httpx
import pytest

from agent_kit.cache import DiskCache
from google_fake import FakeGoogle, docx, xlsx
from gdrive_agent.drive import DriveError, DriveIndex
from gdrive_agent.files import FileReader, Unreadable
from gdrive_agent.kinds import DOC, SHEET, SLIDES


def reader(fake: FakeGoogle, tmp_path, **limits) -> FileReader:
    index = DriveIndex(client=httpx.Client(transport=httpx.MockTransport(fake.handler)), token_provider=lambda: "tok")
    return FileReader(index, DiskCache(tmp_path / "gdrive"), **limits)


def test_a_google_sheet_comes_back_as_text_and_rows(tmp_path):
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, content=xlsx({"Sheet1": [["Quarter", "Revenue"], ["Q3", "48200"]]}))
    got = reader(fake, tmp_path).read("s1")
    assert "Q3\t48200" in got.text.splitlines()
    assert (got.kind, got.columns, got.rows, got.more_tables) == (
        "Google Sheet", ["Quarter", "Revenue"], [["Q3", "48200"]], False)
    assert got.link == "https://drive.google.com/file/d/s1/view"


def test_every_sheet_is_in_the_text_and_the_rows_say_there_is_more(tmp_path):
    # Review Focus 1: the second tab's figures must be readable.
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, content=xlsx({
        "Plan": [["Quarter", "Target"], ["Q3", "50000"]],
        "Actual": [["Quarter", "Revenue"], ["Q3", "48200"]],
    }))
    got = reader(fake, tmp_path).read("s1")
    assert "--- sheet: Actual ---" in got.text and "Q3\t48200" in got.text
    assert got.rows == [["Q3", "50000"]] and got.more_tables is True


def test_a_google_doc_is_converted_to_word_and_read(tmp_path):
    fake = FakeGoogle()
    fake.add("d1", "Spec", DOC, content=docx(["Ship on Friday"]))
    got = reader(fake, tmp_path).read("d1")
    assert got.text == "Ship on Friday" and got.kind == "Google Doc"
    assert fake.requests[-1].url.params["mimeType"].endswith("wordprocessingml.document")


def test_an_uploaded_text_file_is_downloaded_and_read(tmp_path):
    fake = FakeGoogle()
    fake.add("t1", "deed.txt", "text/plain", content=b"Registered office in Girgaon")
    assert reader(fake, tmp_path).read("t1").text == "Registered office in Girgaon"


def test_a_refused_export_reaches_the_reader_with_its_reason(tmp_path):
    # Review Focus 2.
    fake = FakeGoogle()
    fake.add("s1", "Big", SLIDES, export_error="This file is too large to be exported.")
    with pytest.raises(DriveError, match=r"too large to be exported.*10 MB"):
        reader(fake, tmp_path).read("s1")


def test_a_file_its_owner_will_not_let_viewers_download_is_not_fetched(tmp_path):
    # Review Focus 3.
    fake = FakeGoogle()
    fake.add("s1", "Salaries", SHEET, content=b"irrelevant", can_download=False)
    with pytest.raises(Unreadable, match="turned off downloading"):
        reader(fake, tmp_path).read("s1")
    assert fake.asked("export") == 0


def test_downloading_turned_off_after_a_read_is_still_respected(tmp_path):
    # Review Focus 8: the owner's choice is checked before the cache.
    fake = FakeGoogle()
    fake.add("s1", "Salaries", SHEET, content=xlsx({"Sheet1": [["Q3", "1"]]}))
    files = reader(fake, tmp_path)
    files.read("s1")
    fake.add("s1", "Salaries", SHEET, content=xlsx({"Sheet1": [["Q3", "1"]]}), can_download=False)
    with pytest.raises(Unreadable, match="turned off downloading"):
        files.read("s1")


def test_a_file_that_unpacks_past_the_limit_is_refused_with_a_reason(tmp_path):
    # Review Focus 6: a workbook is unzipped and parsed in memory.
    fake = FakeGoogle()
    fake.add("s1", "Huge", SHEET, content=xlsx({"Sheet1": [["Q3", "1"]] * 20}))
    with pytest.raises(Unreadable, match="unpacks to"):
        reader(fake, tmp_path, max_unzipped=100).read("s1")


def test_an_edited_file_is_read_again_and_an_unchanged_one_is_not(tmp_path):
    # Review Focus 4.
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, content=xlsx({"Sheet1": [["Q3", "1"]]}))
    files = reader(fake, tmp_path)
    files.read("s1")
    files.read("s1")
    assert fake.asked("export") == 1
    fake.add("s1", "Budget", SHEET, content=xlsx({"Sheet1": [["Q3", "2"]]}), modified="2026-10-02T09:00:00.000Z")
    assert "Q3\t2" in files.read("s1").text
    assert fake.asked("export") == 2


def test_a_file_past_the_size_limit_is_refused_before_downloading(tmp_path):
    # Review Focus 5.
    fake = FakeGoogle()
    fake.add("p1", "scan.pdf", "application/pdf", content=b"x" * 101)
    with pytest.raises(Unreadable, match="larger than"):
        reader(fake, tmp_path, max_bytes=100).read("p1")
    assert fake.asked("media") == 0


def test_a_video_is_named_and_never_fetched(tmp_path):
    fake = FakeGoogle()
    fake.add("v1", "demo.mp4", "video/mp4", content=b"x")
    with pytest.raises(Unreadable, match=r"demo\.mp4 \(video\)"):
        reader(fake, tmp_path).read("v1")
    assert fake.asked("media") == 0


def test_a_file_the_reader_cannot_parse_says_what_it_is(tmp_path):
    fake = FakeGoogle()
    fake.add("b1", "blob.bin", "application/octet-stream", content=b"\x00\x01\x02")
    with pytest.raises(Unreadable, match="not a format this can read"):
        reader(fake, tmp_path).read("b1")


def test_long_text_is_cut_and_says_so(tmp_path):
    fake = FakeGoogle()
    fake.add("t1", "long.txt", "text/plain", content=b"a" * 50)
    got = reader(fake, tmp_path, max_chars=10).read("t1")
    assert (got.text, got.truncated) == ("a" * 10, True)


def test_the_default_unpacked_limit_fits_the_container():
    """Final review, measured: reading a workbook peaks at about 19x its unpacked
    size (10 MB unpacked -> 241 MB, 25 MB -> 537 MB). With the agent's own ~75 MB,
    the default limit must fit inside the catalog's memory_mb."""
    import json
    from pathlib import Path

    from gdrive_agent.files import MAX_UNZIPPED_BYTES

    entry = json.loads((Path(__file__).resolve().parents[1] / "catalog-1.0.0.json").read_text())
    peak_mb = 22 * MAX_UNZIPPED_BYTES / (1024 * 1024) + 75
    assert peak_mb <= entry["service"]["memory_mb"]


def test_a_damaged_cache_entry_is_read_past_not_reported(tmp_path):
    """Final review: the cache writes in place, so a read that overlaps a write,
    or a container killed mid-write, leaves half an entry behind."""
    fake = FakeGoogle()
    fake.add("t1", "deed.txt", "text/plain", content=b"Registered office in Girgaon")
    files = reader(fake, tmp_path)
    DiskCache(tmp_path / "gdrive").put("gdrive:t1#2026-10-01T10:00:00.000Z", '{"text": "Regist')
    assert files.read("t1").text == "Registered office in Girgaon"
