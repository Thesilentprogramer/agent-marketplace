"""What a Drive file is, and whether and how its text can be read.

Pure: no requests. Google's own files (Docs, Sheets, Slides) have no bytes of
their own; Drive converts each to its Office format, which document_text reads
(a sheet keeps its rows). An uploaded file is downloaded as it is and read the
same way.

What cannot be read is named, with the reason, and never fetched: downloading a
video to find out it holds no text costs the whole video.
"""

from __future__ import annotations

from dataclasses import dataclass

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
SLIDES = "application/vnd.google-apps.presentation"
FOLDER = "application/vnd.google-apps.folder"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@dataclass(frozen=True)
class Kind:
    label: str
    how: str = ""          # "export" or "download"; "" = cannot be read
    export_as: str = ""    # the Office format Drive converts a Google file to
    extension: str = ""    # given to the reader with the converted bytes
    why_not: str = ""

    @property
    def readable(self) -> bool:
        return bool(self.how)


GOOGLE = {
    DOC: Kind("Google Doc", "export", DOCX, ".docx"),
    SHEET: Kind("Google Sheet", "export", XLSX, ".xlsx"),
    SLIDES: Kind("Google Slides", "export", PPTX, ".pptx"),
    FOLDER: Kind("folder", why_not="it is a folder: browse it to see what is inside"),
    "application/vnd.google-apps.shortcut": Kind(
        "shortcut", why_not="it is a shortcut: search for the file it points to"),
    "application/vnd.google-apps.form": Kind("Google Form", why_not="Google offers no text export for forms"),
    "application/vnd.google-apps.drawing": Kind("Google Drawing", why_not="a drawing is a picture, with no text to read"),
}

UPLOADED = {
    "application/pdf": "PDF",
    DOCX: "Word file",
    XLSX: "Excel file",
    PPTX: "PowerPoint file",
    "application/vnd.oasis.opendocument.text": "OpenDocument text",
    "application/vnd.oasis.opendocument.spreadsheet": "OpenDocument spreadsheet",
    "application/vnd.oasis.opendocument.presentation": "OpenDocument presentation",
    "text/csv": "CSV file",
    "text/plain": "text file",
    "text/markdown": "Markdown file",
    "text/html": "HTML file",
    "application/rtf": "RTF file",
    "application/json": "JSON file",
}

OLD_OFFICE = {
    "application/msword": "old Word file (.doc)",
    "application/vnd.ms-excel": "old Excel file (.xls)",
    "application/vnd.ms-powerpoint": "old PowerPoint file (.ppt)",
}

ARCHIVES = {
    "application/zip", "application/x-zip-compressed", "application/vnd.rar",
    "application/x-rar-compressed", "application/x-7z-compressed", "application/gzip", "application/x-tar",
}


def kind_of(mime: str) -> Kind:
    if mime in GOOGLE:
        return GOOGLE[mime]
    if mime.startswith("application/vnd.google-apps."):
        return Kind(f"Google {mime.rsplit('.', 1)[-1]} file", why_not="Google offers no text export for it")
    if mime in OLD_OFFICE:
        return Kind(OLD_OFFICE[mime],
                    why_not="a pre-2007 Office format; saved as .docx, .xlsx or .pptx it can be read")
    if mime in ARCHIVES:
        return Kind("archive", why_not="an archive: its files would have to be unpacked first")
    top = mime.split("/", 1)[0]
    if top in ("image", "video", "audio"):
        return Kind(top, why_not=f"it is {'an' if top in ('image', 'audio') else 'a'} {top}, with no text to read")
    return Kind(UPLOADED.get(mime, "file"), "download")
