import pytest

from gdrive_agent.kinds import DOC, DOCX, PPTX, SHEET, SLIDES, XLSX, kind_of


@pytest.mark.parametrize("mime, label, how", [
    (DOC, "Google Doc", "export"),
    (SHEET, "Google Sheet", "export"),
    (SLIDES, "Google Slides", "export"),
    ("application/pdf", "PDF", "download"),
    (DOCX, "Word file", "download"),
    (XLSX, "Excel file", "download"),
    ("text/csv", "CSV file", "download"),
    # Unknown types are downloaded and the reader decides, refusing by name.
    ("application/octet-stream", "file", "download"),
])
def test_what_can_be_read_and_how(mime, label, how):
    kind = kind_of(mime)
    assert (kind.label, kind.how, kind.readable) == (label, how, True)


def test_googles_own_files_are_converted_to_office_formats():
    assert [(kind_of(m).export_as, kind_of(m).extension) for m in (DOC, SHEET, SLIDES)] == [
        (DOCX, ".docx"), (XLSX, ".xlsx"), (PPTX, ".pptx")]


@pytest.mark.parametrize("mime, label", [
    ("application/vnd.google-apps.folder", "folder"),
    ("application/vnd.google-apps.shortcut", "shortcut"),
    ("application/vnd.google-apps.form", "Google Form"),
    ("application/vnd.google-apps.drawing", "Google Drawing"),
    ("application/vnd.google-apps.vid", "Google vid file"),
    ("image/png", "image"),
    ("video/mp4", "video"),
    ("audio/mpeg", "audio"),
    ("application/zip", "archive"),
    ("application/msword", "old Word file (.doc)"),
])
def test_what_cannot_be_read_says_why(mime, label):
    kind = kind_of(mime)
    assert kind.label == label and not kind.readable and kind.why_not
