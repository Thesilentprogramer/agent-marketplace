"""Google Drive, as far as this agent asks it, for httpx.MockTransport.

Drive answers `size` as a STRING and only for uploaded files; a Google Doc,
Sheet or Slides deck has no size. The fake does the same, so the code is tested
against the shape it will meet.
"""

from __future__ import annotations

import io
import zipfile

import httpx

XLSX_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
WORD_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _zip(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    """A workbook with inline-string and number cells: one worksheet per entry, in order."""
    def cell(value: str) -> str:
        if value.replace(".", "", 1).isdigit():
            return f"<c><v>{value}</v></c>"
        return f'<c t="inlineStr"><is><t>{value}</t></is></c>'

    names = "".join(f'<sheet name="{name}" sheetId="{n}"/>' for n, name in enumerate(sheets, 1))
    parts = {
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": f"<workbook {XLSX_NS}><sheets>{names}</sheets></workbook>",
    }
    for n, rows in enumerate(sheets.values(), 1):
        body = "".join(f"<row>{''.join(cell(v) for v in row)}</row>" for row in rows)
        parts[f"xl/worksheets/sheet{n}.xml"] = f"<worksheet {XLSX_NS}><sheetData>{body}</sheetData></worksheet>"
    return _zip(parts)


def docx(paragraphs: list[str]) -> bytes:
    """A Word document, as Drive's export of a Google Doc arrives."""
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    return _zip({
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": f"<w:document {WORD_NS}><w:body>{body}</w:body></w:document>",
    })


class FakeGoogle:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.list_result: list[str] = []
        self.requests: list[httpx.Request] = []

    def add(self, file_id: str, name: str, mime: str, *, content: bytes = b"",
            modified: str = "2026-10-01T10:00:00.000Z", can_download: bool = True,
            export_error: str = "") -> None:
        self.files[file_id] = {"id": file_id, "name": name, "mimeType": mime, "modifiedTime": modified,
                               "content": content, "can_download": can_download, "export_error": export_error}

    def _details(self, f: dict) -> dict:
        details = {key: f[key] for key in ("id", "name", "mimeType", "modifiedTime")}
        details["webViewLink"] = f"https://drive.google.com/file/d/{f['id']}/view"
        if not f["mimeType"].startswith("application/vnd.google-apps."):
            details["size"] = str(len(f["content"]))
        details["capabilities"] = {"canDownload": f["can_download"]}
        return details

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        parts = request.url.path.split("/")[4:]  # after /drive/v3/files
        if not parts:
            return httpx.Response(200, json={"files": [self._details(self.files[i]) for i in self.list_result]})
        f = self.files.get(parts[0])
        if f is None:
            return httpx.Response(404, json={"error": {"message": "File not found"}})
        if parts[1:] == ["export"]:
            if f["export_error"]:
                return httpx.Response(403, json={"error": {"message": f["export_error"]}})
            return httpx.Response(200, content=f["content"])
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=f["content"])
        return httpx.Response(200, json=self._details(f))

    def asked(self, what: str) -> int:
        test = {
            "export": lambda r: r.url.path.endswith("/export"),
            "media": lambda r: r.url.params.get("alt") == "media",
        }[what]
        return sum(1 for request in self.requests if test(request))
