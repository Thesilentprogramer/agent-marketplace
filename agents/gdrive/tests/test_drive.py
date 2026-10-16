import httpx
import pytest

from google_fake import FakeGoogle
from gdrive_agent.drive import DRIVE_SCOPE, DriveError, DriveIndex
from gdrive_agent.kinds import SHEET, XLSX


def index(fake: FakeGoogle) -> DriveIndex:
    return DriveIndex(client=httpx.Client(transport=httpx.MockTransport(fake.handler)), token_provider=lambda: "tok")


def test_the_scope_reads_contents_and_nothing_more():
    # drive.metadata.readonly may list files but not export or download them.
    assert DRIVE_SCOPE == "https://www.googleapis.com/auth/drive.readonly"


def test_search_looks_inside_every_kind_of_file():
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET)
    fake.list_result = ["s1"]
    listing = index(fake).search("Budget's total")
    params = fake.requests[-1].url.params
    assert params["q"] == "fullText contains 'Budget\\'s total' and trashed=false"
    assert (params["corpora"], params["includeItemsFromAllDrives"]) == ("allDrives", "true")
    assert [(i.id, i.link) for i in listing.items] == [("s1", "https://drive.google.com/file/d/s1/view")]


def test_a_search_returns_at_most_fifty_files_and_says_there_are_more():
    # Every file type counts, so a common word fills a listing fast; 500 files
    # would put about 25k tokens in front of the model.
    fake = FakeGoogle()
    for n in range(60):
        fake.add(f"f{n}", f"Notes {n}", "text/plain")
    fake.list_result = [f"f{n}" for n in range(60)]
    listing = index(fake).search("notes")
    assert (len(listing.items), listing.truncated) == (50, True)


def test_a_files_details_carry_its_size_and_whether_it_may_be_downloaded():
    fake = FakeGoogle()
    fake.add("p1", "deck.pdf", "application/pdf", content=b"x" * 10, can_download=False)
    fake.add("s1", "Budget", SHEET)
    pdf, sheet = index(fake).file("p1"), index(fake).file("s1")
    assert (pdf.size, pdf.can_download, pdf.mime_type) == (10, False, "application/pdf")
    assert (sheet.size, sheet.can_download) == (None, True)


def test_export_asks_drive_for_the_office_format():
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, content=b"xlsx-bytes")
    assert index(fake).export("s1", XLSX) == b"xlsx-bytes"
    request = fake.requests[-1]
    assert request.url.path.endswith("/s1/export") and request.url.params["mimeType"] == XLSX


def test_a_refused_export_gives_googles_reason_and_the_size_limit():
    fake = FakeGoogle()
    fake.add("s1", "Big", SHEET, export_error="This file is too large to be exported.")
    with pytest.raises(DriveError, match=r"too large to be exported.*10 MB"):
        index(fake).export("s1", XLSX)


def test_a_refused_export_for_another_reason_is_not_blamed_on_size():
    fake = FakeGoogle()
    fake.add("s1", "Budget", SHEET, export_error="User rate limit exceeded.")
    with pytest.raises(DriveError, match="rate limit") as caught:
        index(fake).export("s1", XLSX)
    assert "10 MB" not in str(caught.value)


def test_download_reads_an_uploaded_files_bytes():
    fake = FakeGoogle()
    fake.add("p1", "a.pdf", "application/pdf", content=b"%PDF-1.4")
    assert index(fake).download("p1", 1000) == b"%PDF-1.4"
    params = fake.requests[-1].url.params
    assert (params["alt"], params["supportsAllDrives"]) == ("media", "true")


def test_download_refuses_more_bytes_than_allowed():
    fake = FakeGoogle()
    fake.add("p1", "a.pdf", "application/pdf", content=b"x" * 11)
    with pytest.raises(DriveError, match="larger than"):
        index(fake).download("p1", 10)
