# Google Drive Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new catalog agent, Google Drive (`gdrive` 1.0.0), that finds and reads Google Docs, Sheets and Slides, PDFs and Word/Excel/PowerPoint files shared with a Google service account.

**Architecture:** Its own agent service in `agents/gdrive` (catalog kind `mcp`, our own container, served by `agent_kit.mcp_server`), signed in with a service-account key in the catalog form. Drive search covers every file; a reader turns any readable file into text: Google's own files converted by Drive to Office formats, uploads downloaded as they are, both read by a copy of rytangle's `document_text` reader (the one WorkDrive's agent also copies). Published through the global catalog as a new agent, so every server can add it beside its other tools.

**Tech Stack:** Python 3.12, httpx, LangChain tools, `agent_kit` (MCP server, rows, cache, settings), google-auth, pypdf, pytest with `httpx.MockTransport`. Repo: `kaliperdev/agent-marketplace` (default branch `main`).

**Spec:** the "Design" section below, decided in conversation on 2026-10-14 (no separate spec file).

## Design

**Our own agent with a service account, not Google's Drive MCP server or "Sign in with Google":**

| | Our agent + service account (chosen) | Google's Drive MCP server (`drivemcp.googleapis.com`) | Our agent + "Sign in with Google" |
|---|---|---|---|
| Status | Google's stable Drive API | Developer Preview (May 2026), not generally available | Stable API |
| Client setup | One key file; share folders with its email | A Google Cloud OAuth app per client, preview enrolment | A Google Cloud OAuth app per client; `drive.readonly` is a restricted scope (Internal Workspace apps only, else Google review) |
| What it can see | Only what is shared with the account: an explicit boundary | Everything the signed-in person sees | Everything the signed-in person sees |
| Read-only | By construction: no write tool exists | Its tools include `create_file` and `copy_file`; only the entry's tool list keeps it to reading | By construction |
| Sheets as rows (charts, counts) | Yes (`agent_kit.rows.table`) | No: a vendor server's tools return text | Yes |

Revisit Google's server when it is generally available: it would be another entry (`service.url`, `connection.method: "signin"`).

**Separate from Google Docs, by Sahil's choice (2026-10-14).** Google Docs (`gdocs` 2.0.1) and WorkDrive are not touched: no file under `agents/gdocs`, `agents/workdrive` or `agents/kit` changes. Google Drive is a new id, folder, package and router source (`gdrive`). Consequences:
- A server adds it like any new agent and uploads a key; the same key file as Google Docs works (it needs the Drive API on, which Google Docs already uses for search).
- It is not pre-filled from a server's `.env`: rytangle's `KEY_OWNERS` (`router/app/local_store.py:245`) gives `GOOGLE_*` settings to `gdocs`. Uploading the key in the form is the way, and needs no rytangle change.
- **Google Drive replaces Google Docs wherever it is turned on** (decided 2026-10-14 after review). It sees every Google Doc that Google Docs sees, and the planner asks every document store about a named file at once, so running both would search the same Docs twice and pay for one more source on every such question. Task 7 switches Google Docs off on each server where Drive goes on.

**What is read, and how (one Google scope: `drive.readonly`):**

| File | How | Becomes |
|---|---|---|
| Google Doc | Drive export to `.docx` | text, tables row by row |
| Google Sheet | Drive export to `.xlsx` | text of every sheet, plus the first sheet as rows |
| Google Slides | Drive export to `.pptx` | text, slide by slide |
| Uploaded PDF, Word, Excel, PowerPoint, OpenDocument, CSV, text, HTML, RTF | Drive download | as above |
| Folder, shortcut, Form, Drawing, other Google types, image, video, audio, archive, `.doc/.xls/.ppt` | not fetched | "cannot be read" with the reason |

Limits, each reported in words: Drive converts at most 10 MB; downloads stop at 25 MB; text stops at 200,000 characters (marked TRUNCATED); scanned PDFs have no text (no OCR); a file whose owner turned off downloading for viewers cannot be read.

## Global Constraints

- Every code block in this plan was **written from reading the code, not run**. Run each step's command and trust its output over this text.
- **Do not change** anything under `agents/gdocs`, `agents/workdrive`, `agents/kit`, or any existing `catalog-*.json`. Every change is inside `agents/gdrive/`, plus `published/gdrive/` when published.
- Agents run Python `>=3.11`, built on `python:3.12-slim`.
- One scope: `https://www.googleapis.com/auth/drive.readonly`. No write scope, no write tool.
- Catalog id, router source and router agent name: `gdrive`. Package `kaliper/agent-gdrive:1.0.0`. `needs_router` `"0.4.0"` (`holds_documents` and `service.memory_mb` are 0.4.0 keys; servers run 0.7.0).
- The form field is `GOOGLE_SA_JSON` (a `file` field: the service receives the key's contents).
- An empty search returns `agent_kit.rows.nothing_found(...)`: the router recognises "no matches for:".
- Published versions are locked: never edit `published/`; a change after publishing is a new version.
- Commit messages describe the change only: no tool or AI attribution, no `Co-Authored-By` trailer.
- Run the agent's tests from its folder (`cd agents/gdrive && uv run pytest -q`) and the entry tests from the repo root (`uv run pytest tests/test_entry.py -q`).

## Review Focus

1. **A workbook with several sheets:** someone asking about the second tab expects its figures. The text carries every sheet; the rows carry the first and say there is more (`more_tables`). Pinned in Task 4.
2. **A Google file larger than Drive's 10 MB conversion limit:** expect Google's reason plus "10 MB", not a bare 403. Pinned in Task 3 and Task 4.
3. **An owner who turned off downloading for viewers:** expect "turned off downloading" and nothing fetched. Pinned in Task 4.
4. **A file edited after it was read:** expect the new contents; an unchanged file is not fetched again. Pinned in Task 4.
5. **A huge upload (a 2 GB video, a 300 MB PDF):** refused before any bytes are downloaded. Pinned in Task 4 (size) and Task 2 (a video is never fetched).
6. **A spreadsheet that unpacks to hundreds of MB:** refused with a reason, not a container that runs out of memory (384 MB). Pinned in Task 4.
7. **A conversion refused for a reason other than size (rate limit, permission):** Google's reason, never "10 MB". Pinned in Task 3.
8. **Downloading turned off after a file was read:** still refused, not served from the cache. Pinned in Task 4.

---

### Task 0: Branch

**Files:** none.

- [ ] **Step 1: Check the starting point**

Run: `cd ~/Documents/agent-marketplace && git fetch && git log origin/main..HEAD --oneline && git status --short`
Expected on 2026-10-14: `bb1b7f4 notion 1.0.1: …` (published to the hosted catalog, not pushed; checked against `git branch -r --contains bb1b7f4`, which lists nothing) and an untracked `docs/superpowers/`. Ask Sahil before going on if anything else is listed.

- [ ] **Step 2: Branch from here, so the Notion record travels with this work**

```bash
git switch -c feat/gdrive-agent
```

---

### Task 1: The agent's folder and its file reader

The package skeleton (shaped like `agents/gdocs`) and a copy of rytangle's `document_text.py` with rytangle's 29 tests, as `agents/workdrive` copies it. The copy is the established pattern for agent services; nothing shared changes.

**Files:**
- Create: `agents/gdrive/pyproject.toml`, `agents/gdrive/uv.lock` (by `uv lock`), `agents/gdrive/Dockerfile`
- Create: `agents/gdrive/gdrive_agent/__init__.py` (empty), `agents/gdrive/gdrive_agent/document_text.py`
- Test: `agents/gdrive/tests/test_document_text.py`

**Interfaces:**
- Produces: `gdrive_agent.document_text.extract(data: bytes, filename: str = "") -> Extracted`; `Extracted(text: str, kind: str, columns: list[str] | None = None, rows: list[list[str]] | None = None, more_tables: bool = False)` (frozen dataclass); `UnreadableDocument(RuntimeError)`.

- [ ] **Step 1: Write the package files and copy rytangle's tests**

`agents/gdrive/pyproject.toml`:

```toml
[project]
name = "gdrive-agent"
version = "1.0.0"
description = "Google Drive as an agent service: its tools over MCP (POST /mcp, GET /health)."
requires-python = ">=3.11"
dependencies = ["httpx>=0.27", "langchain-core>=1.0", "google-auth[requests]>=2.56.3", "pypdf>=6.14.2", "agent-kit"]

[tool.uv.sources]
agent-kit = { path = "../kit" }

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["gdrive_agent"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`agents/gdrive/Dockerfile`:

```dockerfile
# The Google Drive agent service. Built from agents/ so the shared kit is included:
#   docker build -f agents/gdrive/Dockerfile -t kaliper/agent-gdrive:1.0.0 agents
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
WORKDIR /app
COPY kit /kit
COPY gdrive/pyproject.toml gdrive/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY gdrive/gdrive_agent ./gdrive_agent
RUN uv sync --frozen --no-dev
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
# The environment was built above; running it directly skips a re-sync on every start.
CMD ["/app/.venv/bin/python", "-m", "gdrive_agent.server"]
```

```bash
cd ~/Documents/agent-marketplace
mkdir -p agents/gdrive/gdrive_agent agents/gdrive/tests
: > agents/gdrive/gdrive_agent/__init__.py
sed 's/^from app\.tools\.document_text import/from gdrive_agent.document_text import/' \
  ~/Documents/Demo-rytanlge/router/tests/test_document_text.py > agents/gdrive/tests/test_document_text.py
cd agents/gdrive && uv lock
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd agents/gdrive && uv run pytest tests/test_document_text.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'gdrive_agent.document_text'`.

- [ ] **Step 3: Copy the reader in, saying where it came from**

```bash
cd ~/Documents/agent-marketplace
{ printf '%s\n' \
  "# Copied from rytangle router/app/tools/document_text.py, as agents/workdrive's copy is. Unchanged."
  cat ~/Documents/Demo-rytanlge/router/app/tools/document_text.py; } > agents/gdrive/gdrive_agent/document_text.py
```

- [ ] **Step 4: Run the tests**

Run: `cd agents/gdrive && uv run pytest -q`
Expected: `29 passed` (pypdf is a dependency, so the PDF tests run).

- [ ] **Step 5: Commit**

```bash
git add agents/gdrive
git commit -m "gdrive: the agent's package, with rytangle's document_text reader and its tests"
```

---

### Task 2: What each kind of Drive file is, and how it is read

A pure table: no requests. Everything else asks it.

**Files:**
- Create: `agents/gdrive/gdrive_agent/kinds.py`
- Test: `agents/gdrive/tests/test_kinds.py`

**Interfaces:**
- Produces: constants `DOC`, `SHEET`, `SLIDES`, `FOLDER`, `DOCX`, `XLSX`, `PPTX` (MIME type strings); `Kind(label: str, how: str = "", export_as: str = "", extension: str = "", why_not: str = "")` frozen dataclass with property `readable -> bool`; `kind_of(mime: str) -> Kind`. `how` is `"export"`, `"download"`, or `""` (cannot be read).

- [ ] **Step 1: Write the failing test**

`agents/gdrive/tests/test_kinds.py`:

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd agents/gdrive && uv run pytest tests/test_kinds.py -q`
Expected: `ModuleNotFoundError: No module named 'gdrive_agent.kinds'`.

- [ ] **Step 3: Write `kinds.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `cd agents/gdrive && uv run pytest -q`
Expected: `48 passed` (document_text 29, kinds 19).

- [ ] **Step 5: Commit**

```bash
git add agents/gdrive/gdrive_agent/kinds.py agents/gdrive/tests/test_kinds.py
git commit -m "gdrive: kinds.py names every Drive file kind and how its text is read"
```

---

### Task 3: Drive: list, search, a file's details, and its bytes

Shaped on `agents/gdocs/gdocs_agent/drive.py` (that file is not changed). The tests use a fake Google behind `httpx.MockTransport`, which Tasks 4 and 5 reuse.

**Files:**
- Create: `agents/gdrive/gdrive_agent/drive.py`
- Create: `agents/gdrive/tests/google_fake.py`
- Test: `agents/gdrive/tests/test_drive.py`

**Interfaces:**
- Produces: `DRIVE_SCOPE`; `EXPORT_LIMIT_MB = 10`; `SEARCH_MAX_ITEMS = 50`; `DriveError(RuntimeError)`; `DriveItem(id, name, mime_type, modified, link="", size: int | None = None, can_download: bool = True)` with property `is_folder`; `DriveListing(items, truncated)`; `DriveIndex(client, token_provider, max_items=MAX_ITEMS)` with `.max_items`, `.shared_roots() -> DriveListing`, `.children(folder_id) -> DriveListing`, `.search(query) -> DriveListing`, `.file(file_id) -> DriveItem`, `.export(file_id, mime) -> bytes`, `.download(file_id, max_bytes) -> bytes`.
- Test helper produces: `google_fake.FakeGoogle` with `.add(file_id, name, mime, *, content=b"", modified=..., can_download=True, export_error="")`, `.list_result: list[str]`, `.requests`, `.handler(request)`, `.asked(what) -> int` for `"export"` or `"media"`; `google_fake.xlsx(sheets: dict[str, list[list[str]]]) -> bytes`; `google_fake.docx(paragraphs: list[str]) -> bytes`.

- [ ] **Step 1: Write the fake Google and the failing tests**

`agents/gdrive/tests/google_fake.py`:

```python
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
```

`agents/gdrive/tests/test_drive.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd agents/gdrive && uv run pytest tests/test_drive.py -q`
Expected: `ModuleNotFoundError: No module named 'gdrive_agent.drive'`.

- [ ] **Step 3: Write `drive.py`**

```python
# Shaped on agents/gdocs/gdocs_agent/drive.py (itself copied from rytangle's
# router/app/tools/drive.py), which stays as it is. This one also reads bytes.
"""Read-only Google Drive: what files exist, where, and their bytes.

Two facts, both verified against a live service account for the Google Docs
agent rather than taken from documentation prose:

- `sharedWithMe` returns only the items shared with the account DIRECTLY. A
  folder shared with the account appears; the files nested inside it do not,
  even though they are readable through inherited permission.
- `fullText contains` DOES reach those nested files, at any depth, in one call.
  It searches names and contents of every type Drive indexes, so search is what
  makes nesting a non-problem; browsing is only for orientation.

Reading contents needs `drive.readonly`; `drive.metadata.readonly` may list
files but not export or download them. Nothing here writes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

DRIVE_API = "https://www.googleapis.com/drive/v3/files"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"

LIST_FIELDS = "files(id,name,mimeType,modifiedTime,webViewLink),nextPageToken"
FILE_FIELDS = "id,name,mimeType,modifiedTime,size,webViewLink,capabilities/canDownload"
PAGE_SIZE = 100
# The Google Docs agent's ceiling (it measured 329 Docs on one account and chose
# 500 with headroom). A ceiling, so a large Drive cannot flood the aggregator;
# every file type counts toward it here, so "list everything" reaches it sooner.
MAX_ITEMS = 500
# A search returns at most this many: every file type counts toward it, and the
# list goes to the model whole. Browsing a folder keeps MAX_ITEMS.
SEARCH_MAX_ITEMS = 50
EXPORT_LIMIT_MB = 10  # Drive's own limit on converted content (files.export)
DOWNLOAD_TIMEOUT_SECONDS = 60.0

TokenProvider = Callable[[], str]


class DriveError(RuntimeError):
    """A Drive request was refused or returned unusable data."""


@dataclass(frozen=True)
class DriveItem:
    id: str
    name: str
    mime_type: str
    modified: str
    link: str = ""
    size: int | None = None      # bytes; None for Google's own files, which have none
    can_download: bool = True    # False when the owner turned downloading off for viewers

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


@dataclass(frozen=True)
class DriveListing:
    items: list[DriveItem]
    truncated: bool


def escape_query_value(value: str) -> str:
    """Escape a user string for a Drive query literal.

    The model chooses the search term, so an unescaped apostrophe would end the
    literal early and the rest of the term would be parsed as query syntax.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _item(raw: dict) -> DriveItem:
    size = raw.get("size")
    return DriveItem(
        id=raw["id"],
        name=raw.get("name", ""),
        mime_type=raw.get("mimeType", ""),
        modified=raw.get("modifiedTime", ""),
        link=raw.get("webViewLink", ""),
        size=int(size) if str(size or "").isdigit() else None,
        can_download=bool((raw.get("capabilities") or {}).get("canDownload", True)),
    )


def _reason(response: httpx.Response) -> str:
    """Google's own sentence for a refusal, else the start of the body."""
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return response.text[:200]


class DriveIndex:
    def __init__(
        self,
        client: httpx.Client,
        token_provider: TokenProvider,
        max_items: int = MAX_ITEMS,
    ) -> None:
        self.client = client
        self.token_provider = token_provider
        self.max_items = max_items

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token_provider()}"}

    def _list(self, query: str, limit: int | None = None) -> DriveListing:
        limit = limit or self.max_items
        items: list[DriveItem] = []
        truncated = False
        page_token: str | None = None

        while True:
            params = {
                "q": query,
                "fields": LIST_FIELDS,
                "pageSize": str(PAGE_SIZE),
                # Sent unconditionally so adding the service account to a Shared
                # Drive later needs no code change. corpora=allDrives is what
                # reaches Shared Drives (Google's documentation; confirm live in
                # Task 7, Step 4).
                "corpora": "allDrives",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token

            response = self.client.get(DRIVE_API, params=params, headers=self._headers())
            if response.status_code != 200:
                raise DriveError(f"drive query {query!r} returned {response.status_code}: {_reason(response)}")
            payload = response.json()
            items.extend(_item(raw) for raw in payload.get("files", []))

            page_token = payload.get("nextPageToken")
            if len(items) >= limit:
                truncated = len(items) > limit or bool(page_token)
                del items[limit:]
                break
            if not page_token:
                break

        return DriveListing(items=items, truncated=truncated)

    def shared_roots(self) -> DriveListing:
        """The items shared with this account directly -- typically folders."""
        return self._list("sharedWithMe and trashed=false")

    def children(self, folder_id: str) -> DriveListing:
        return self._list(f"'{escape_query_value(folder_id)}' in parents and trashed=false")

    def search(self, query: str) -> DriveListing:
        """Every file whose name or contents match, of any type."""
        return self._list(f"fullText contains '{escape_query_value(query)}' and trashed=false",
                          limit=min(SEARCH_MAX_ITEMS, self.max_items))

    def file(self, file_id: str) -> DriveItem:
        response = self.client.get(
            f"{DRIVE_API}/{file_id}",
            params={"fields": FILE_FIELDS, "supportsAllDrives": "true"},
            headers=self._headers(),
        )
        if response.status_code == 404:
            raise DriveError(f"no file with id {file_id} is shared with this account")
        if response.status_code != 200:
            raise DriveError(f"file {file_id} returned {response.status_code}: {_reason(response)}")
        return _item(response.json())

    def export(self, file_id: str, mime: str) -> bytes:
        """A Google Doc, Sheet or Slides deck converted to `mime` by Drive."""
        response = self.client.get(
            f"{DRIVE_API}/{file_id}/export",
            params={"mimeType": mime},
            headers=self._headers(),
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            reason = _reason(response)
            # The size sentence only when size is Google's reason: a rate limit
            # or a refused key must not read as "file too large".
            too_big = "too large" in reason.lower() or "exportSizeLimitExceeded" in response.text
            raise DriveError(
                f"Google would not convert file {file_id} ({response.status_code}: {reason})."
                + (f" Google converts files of up to {EXPORT_LIMIT_MB} MB; a larger one can only be opened in Drive."
                   if too_big else "")
            )
        return response.content

    def download(self, file_id: str, max_bytes: int) -> bytes:
        """An uploaded file's bytes, as stored: streamed, and stopped past max_bytes,
        so a file whose size Drive did not report cannot fill the container."""
        with self.client.stream(
            "GET",
            f"{DRIVE_API}/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            headers=self._headers(),
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code != 200:
                response.read()
                raise DriveError(f"downloading file {file_id} returned {response.status_code}: {_reason(response)}")
            data = bytearray()
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > max_bytes:
                    raise DriveError(f"file {file_id} is larger than the {max_bytes // (1024 * 1024)} MB this reads")
        return bytes(data)
```

- [ ] **Step 4: Run the tests**

Run: `cd agents/gdrive && uv run pytest -q`
Expected: `57 passed`.

- [ ] **Step 5: Commit**

```bash
git add agents/gdrive/gdrive_agent/drive.py agents/gdrive/tests/google_fake.py agents/gdrive/tests/test_drive.py
git commit -m "gdrive: Drive listing, search over every file type, a file's details, export and download"
```

---

### Task 4: One reader for any readable file

**Files:**
- Create: `agents/gdrive/gdrive_agent/files.py`
- Test: `agents/gdrive/tests/test_files.py`

**Interfaces:**
- Consumes: `DriveIndex.file/export/download`, `DriveItem` (Task 3); `kind_of`, `Kind` (Task 2); `extract`, `Extracted`, `UnreadableDocument` (Task 1); `agent_kit.cache.DiskCache(root)` with `.get(key) -> str | None`, `.put(key, value)`.
- Produces: `MAX_CHARS = 200_000`, `MAX_BYTES = 25 * 1024 * 1024`; `Unreadable(RuntimeError)`; `FileText(name, link, kind, text, truncated, columns=None, rows=None, more_tables=False)`; `MAX_UNZIPPED_BYTES = 100 * 1024 * 1024`; `FileReader(index, cache, max_chars=MAX_CHARS, max_bytes=MAX_BYTES, max_unzipped=MAX_UNZIPPED_BYTES)` with `.read(file_id) -> FileText`. Raises `Unreadable` for a file that exists but cannot be read; lets `DriveError` through.

- [ ] **Step 1: Write the failing tests (Review Focus 1-5 included)**

`agents/gdrive/tests/test_files.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd agents/gdrive && uv run pytest tests/test_files.py -q`
Expected: `ModuleNotFoundError: No module named 'gdrive_agent.files'`.

- [ ] **Step 3: Write `files.py`**

```python
"""Any readable Drive file's text: the one entry point read_drive_file uses.

How depends on the kind (kinds.py): Google's own files converted by Drive to
their Office format, uploaded files downloaded as they are. Both become text in
document_text, so a sheet keeps its rows and a PDF its words.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict, dataclass

from agent_kit.cache import DiskCache
from gdrive_agent.document_text import Extracted, UnreadableDocument, extract
from gdrive_agent.drive import DriveIndex, DriveItem
from gdrive_agent.kinds import Kind, kind_of

MAX_CHARS = 200_000
MAX_BYTES = 25 * 1024 * 1024
# Office files are zips, and the reader parses each part whole: a 10 MB workbook
# can unpack to hundreds of MB inside a 384 MB container.
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024


class Unreadable(RuntimeError):
    """The file exists and cannot be turned into text; the message says why."""


@dataclass(frozen=True)
class FileText:
    name: str
    link: str
    kind: str
    text: str
    truncated: bool
    """The first sheet as a table, for a spreadsheet; None for prose.

    `more_tables` is the rows' own flag, not `truncated`: cutting the text at a
    character limit drops no row, and a second sheet is never in the rows.
    """
    columns: list[str] | None = None
    rows: list[list[str]] | None = None
    more_tables: bool = False


class FileReader:
    def __init__(self, index: DriveIndex, cache: DiskCache,
                 max_chars: int = MAX_CHARS, max_bytes: int = MAX_BYTES,
                 max_unzipped: int = MAX_UNZIPPED_BYTES) -> None:
        self.index, self.cache = index, cache
        self.max_chars, self.max_bytes, self.max_unzipped = max_chars, max_bytes, max_unzipped

    def read(self, file_id: str) -> FileText:
        item = self.index.file(file_id)
        kind = kind_of(item.mime_type)
        if not kind.readable:
            raise Unreadable(f"{item.name} ({kind.label}): {kind.why_not}")
        got = self._extracted(item, kind)
        return FileText(
            name=item.name, link=item.link, kind=kind.label,
            text=got.text[: self.max_chars], truncated=len(got.text) > self.max_chars,
            columns=got.columns, rows=got.rows, more_tables=got.more_tables,
        )

    def _extracted(self, item: DriveItem, kind: Kind) -> Extracted:
        # Keyed by revision: DiskCache never expires, so an edited file must miss.
        key = f"gdrive:{item.id}#{item.modified}"
        # Before the cache: an owner can turn downloading off without editing the
        # file, and a cached copy must not outlive that choice.
        if not item.can_download:
            raise Unreadable(
                f"{item.name} ({kind.label}): its owner turned off downloading and copying for the people "
                "it is shared with, so its contents cannot be read here"
            )
        cached = self.cache.get(key)
        if cached is not None:
            return Extracted(**json.loads(cached))
        if kind.how == "export":
            data, filename = self.index.export(item.id, kind.export_as), item.name + kind.extension
        else:
            if item.size is not None and item.size > self.max_bytes:
                raise Unreadable(
                    f"{item.name} ({kind.label}) is larger than the {self.max_bytes // (1024 * 1024)} MB "
                    "this reads; open it in Drive"
                )
            data, filename = self.index.download(item.id, self.max_bytes), item.name
        self._refuse_if_it_unpacks_too_large(item, kind, data)
        try:
            got = extract(data, filename)
        except UnreadableDocument as error:
            raise Unreadable(str(error)) from None
        self.cache.put(key, json.dumps(asdict(got)))
        return got

    def _refuse_if_it_unpacks_too_large(self, item: DriveItem, kind: Kind, data: bytes) -> None:
        if not data.startswith(b"PK"):
            return
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                total = sum(part.file_size for part in archive.infolist())
        except zipfile.BadZipFile:
            return  # extract says what it is
        if total > self.max_unzipped:
            raise Unreadable(
                f"{item.name} ({kind.label}) unpacks to {total // (1024 * 1024)} MB, more than the "
                f"{self.max_unzipped // (1024 * 1024)} MB this reads; open it in Drive"
            )
```

- [ ] **Step 4: Run the tests**

Run: `cd agents/gdrive && uv run pytest -q`
Expected: `70 passed`.

- [ ] **Step 5: Commit**

```bash
git add agents/gdrive/gdrive_agent/files.py agents/gdrive/tests/test_files.py
git commit -m "gdrive: FileReader reads Docs, Sheets, Slides and uploaded files, refusing by name what it cannot"
```

---

### Task 5: The tools, and the server that offers them

**Files:**
- Create: `agents/gdrive/gdrive_agent/tools.py`, `agents/gdrive/gdrive_agent/server.py`
- Test: `agents/gdrive/tests/test_tools.py`, `agents/gdrive/tests/test_server.py`

**Interfaces:**
- Consumes: `DriveIndex`, `DriveItem`, `DriveListing`, `DRIVE_SCOPE` (Task 3); `FileReader`, `Unreadable` (Task 4); `kind_of` (Task 2); `agent_kit.rows.table`, `no_rows`, `nothing_found`; `agent_kit.settings.credential`, `missing`; `agent_kit.mcp_server.serve(tools, port, ready_error, name=...)`.
- Produces: `make_drive_tools(index: DriveIndex, reader: FileReader) -> list[BaseTool]` (tools `browse_drive`, `search_drive`, `read_drive_file`); `server.key_path(value, key_dir=None) -> str`; `server.build_tools(env, client=None, key_dir=None) -> tuple[list, str | None]`; `server.main()`.

- [ ] **Step 1: Write the failing tests**

`agents/gdrive/tests/test_tools.py`:

```python
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
```

`agents/gdrive/tests/test_server.py`:

```python
import os
import stat
from pathlib import Path

from gdrive_agent.server import build_tools, key_path

KEY = '{"type": "service_account", "client_email": "reader@example.invalid"}'


def test_the_server_offers_the_three_drive_tools(tmp_path):
    tools, problem = build_tools({"GOOGLE_SA_JSON": KEY, "CACHE_DIR": str(tmp_path)}, key_dir=tmp_path)
    assert problem is None
    assert sorted(t.name for t in tools) == ["browse_drive", "read_drive_file", "search_drive"]


def test_the_key_can_arrive_as_its_contents_and_is_kept_private(tmp_path):
    path = key_path(KEY, tmp_path)
    assert Path(path).read_text(encoding="utf-8") == KEY
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_key_can_still_be_a_path(tmp_path):
    assert key_path("/run/keys/sa.json", tmp_path) == "/run/keys/sa.json"


def test_without_its_key_it_offers_nothing_and_says_why(tmp_path):
    assert build_tools({}, key_dir=tmp_path) == ([], "GOOGLE_SA_JSON is not set")
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd agents/gdrive && uv run pytest tests/test_tools.py tests/test_server.py -q`
Expected: `ModuleNotFoundError` for `gdrive_agent.tools` and `gdrive_agent.server`.

- [ ] **Step 3: Write `tools.py` and `server.py`**

`agents/gdrive/gdrive_agent/tools.py`:

```python
"""The agent's three tools: browse and search Drive, and read any file's text."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from agent_kit.rows import no_rows, nothing_found, table
from gdrive_agent.drive import DriveIndex, DriveItem, DriveListing
from gdrive_agent.files import FileReader, Unreadable
from gdrive_agent.kinds import kind_of

COLUMNS = ["name", "id", "kind", "modified"]


def _link(item: DriveItem) -> str:
    """Drive's own link; built from the id when Drive gave none. A folder and a
    file open at DIFFERENT addresses: a file URL for a folder is a dead page."""
    if item.link:
        return item.link
    if item.is_folder:
        return f"https://drive.google.com/drive/folders/{item.id}"
    return f"https://drive.google.com/file/d/{item.id}/view"


def _kind(item: DriveItem) -> str:
    kind = kind_of(item.mime_type)
    return kind.label if kind.readable or item.is_folder else f"{kind.label}, cannot be read"


def _ordered(items: list[DriveItem]) -> list[DriveItem]:
    """Folders first, then files, each by name. Drive's order is not stable, and
    an unstable tool result makes an unstable prompt."""
    return sorted(items, key=lambda i: (not i.is_folder, i.name))


def _format(listing: DriveListing, empty: str, max_items: int) -> str:
    lines = [
        f"FOLDER\t{i.id}\t{i.name}\t{_link(i)}" if i.is_folder
        else f"FILE\t{i.id}\t{i.name}\t{_kind(i)}\t(modified {i.modified[:10]})\t{_link(i)}"
        for i in _ordered(listing.items)
    ]
    if not lines:
        return empty
    if listing.truncated:
        lines.append(f"(listing capped at {max_items} items; there are more)")
    return "\n".join(lines)


def _rows(listing: DriveListing) -> dict:
    rows = [[i.name, i.id, _kind(i), str(i.modified or "")[:10]] for i in _ordered(listing.items)]
    return table(COLUMNS, rows, truncated=listing.truncated)


def make_drive_tools(index: DriveIndex, reader: FileReader) -> list[BaseTool]:
    @tool(response_format="content_and_artifact")
    def browse_drive(folder_id: str = "") -> tuple:
        """List what is in Drive. Call with no folder_id to see what is shared with
        you, then call it again with a folder's id to see inside that folder.
        Files nested in subfolders are only visible by descending into them, so
        prefer search_drive when you know what you are looking for. Each file says
        what kind it is; one marked "cannot be read" exists, but its contents are
        not readable."""
        if folder_id:
            listing = index.children(folder_id)
            empty = f"empty: folder {folder_id} contains nothing"
        else:
            listing = index.shared_roots()
            empty = "empty: nothing is shared with this account"
        return _format(listing, empty, index.max_items), _rows(listing) if listing.items else no_rows()

    @tool(response_format="content_and_artifact")
    def search_drive(query: str) -> tuple:
        """Find files whose name or contents contain a word or phrase: Google Docs,
        Sheets and Slides, PDFs, and Word, Excel and PowerPoint files. This searches
        every file you can reach, however deeply nested, so it is the fastest way to
        locate material. Returns ids to pass to read_drive_file."""
        listing = index.search(query)
        if not listing.items:
            return nothing_found(query, "the files shared with this account")
        return _format(listing, "no matches", index.max_items), _rows(listing)

    @tool(response_format="content_and_artifact")
    def read_drive_file(file_id: str) -> tuple:
        """Read the TEXT INSIDE one file, by the id shown by search_drive or
        browse_drive. Readable: Google Docs, Sheets and Slides; PDFs with
        selectable text; Word, Excel and PowerPoint; OpenDocument; CSV and plain
        text. A spreadsheet comes back one row per line with cells tab-separated,
        every sheet in turn.

        Not readable, and each says why rather than coming back empty: scanned
        PDFs, images, video, audio, forms, archives, old .doc/.xls/.ppt files, very
        large files, and files whose owner turned off downloading. When a file
        cannot be read, say it exists and its contents are not readable -- never
        guess them from its name."""
        try:
            got = reader.read(file_id)
        except Unreadable as error:
            return (f"cannot be read: {error}. The file exists; say so, and never guess its contents "
                    "from its name.", no_rows())
        except Exception as error:  # noqa: BLE001 - reported to the model as text
            return f"google drive error: {error}", no_rows()
        head = f"=== {got.name} ({got.kind}) === {got.link}"
        if got.truncated:
            # Declared, never silent: an answer drawn from a shortened source that
            # did not say so is indistinguishable from a complete one.
            head += " (TRUNCATED -- the file continues past what is shown)"
        payload = (table(got.columns, got.rows, truncated=got.more_tables)
                   if got.columns and got.rows else no_rows())
        return f"{head}\n{got.text}", payload

    return [browse_drive, search_drive, read_drive_file]
```

`agents/gdrive/gdrive_agent/server.py` (`key_path` and the token provider are copied from `agents/gdocs`, which is not changed):

```python
"""Google Drive as its own MCP server (catalog kind "mcp", agent id gdrive).

GOOGLE_SA_JSON is the service account's key: the client's settings service
passes the key file's CONTENTS (a path on that server means nothing in here),
which are written to a private file for Google's library. A path still works,
for running this by hand.

  python -m gdrive_agent.server
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import httpx

from agent_kit.cache import DiskCache
from agent_kit.mcp_server import serve
from agent_kit.settings import credential, missing
from gdrive_agent.drive import DRIVE_SCOPE, DriveIndex
from gdrive_agent.files import FileReader
from gdrive_agent.tools import make_drive_tools

HTTP_TIMEOUT_SECONDS = 30.0


def key_path(value: str, key_dir: Path | None = None) -> str:
    """A path to the key: the value itself, or a private file holding it."""
    if not value.lstrip().startswith("{"):
        return value
    handle, path = tempfile.mkstemp(prefix="sa-", suffix=".json", dir=key_dir)
    with os.fdopen(handle, "w", encoding="utf-8") as out:  # mkstemp makes it 0600
        out.write(value)
    return path


def service_account_token_provider(sa_json_path: str, scopes: Sequence[str]) -> Callable[[], str]:
    """Mint access tokens from a service-account key file for the given scopes."""

    # Built once and refreshed only when expired (tokens last an hour): minting a
    # new token on every call cost two extra round trips per file read.
    held: dict = {}

    def provide() -> str:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        credentials = held.get("credentials")
        if credentials is None:
            with open(sa_json_path, encoding="utf-8") as handle:
                info = json.load(handle)
            credentials = held["credentials"] = service_account.Credentials.from_service_account_info(
                info, scopes=list(scopes))
        if not credentials.valid:
            credentials.refresh(Request())
        return str(credentials.token)

    return provide


def build_tools(env: Mapping[str, str], client: httpx.Client | None = None,
                key_dir: Path | None = None) -> tuple[list, str | None]:
    """The tools, or none and why."""
    problem = missing(env, ["GOOGLE_SA_JSON"])
    if problem:
        return [], problem
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    token_provider = service_account_token_provider(key_path(credential(env, "GOOGLE_SA_JSON"), key_dir),
                                                    (DRIVE_SCOPE,))
    index = DriveIndex(client=client, token_provider=token_provider)
    reader = FileReader(index, DiskCache(Path(env.get("CACHE_DIR") or ".cache") / "gdrive"))
    return list(make_drive_tools(index, reader)), None


def main() -> None:
    tools, problem = build_tools(os.environ)
    serve(tools, int(os.environ.get("PORT") or 8080), problem, name="gdrive")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `cd agents/gdrive && uv run pytest -q`
Expected: `79 passed` (document_text 29, kinds 19, drive 9, files 13, tools 5, server 4).

- [ ] **Step 5: Commit**

```bash
git add agents/gdrive
git commit -m "gdrive: browse_drive, search_drive and read_drive_file, served over MCP"
```

---

### Task 6: The catalog entry

**Files:**
- Create: `agents/gdrive/catalog-1.0.0.json`
- Modify: `agents/gdrive/tests/test_server.py`

**Interfaces:**
- Consumes: the three tool names and their docstrings (Task 5).
- Produces: a valid entry `gdrive` 1.0.0 naming package `kaliper/agent-gdrive:1.0.0`, which Task 7 uploads.

- [ ] **Step 1: Point the server test at the entry, so it fails until the entry exists**

In `agents/gdrive/tests/test_server.py`, add `import json` to the imports and replace `test_the_server_offers_the_three_drive_tools` with:

```python
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
```

Run: `cd agents/gdrive && uv run pytest tests/test_server.py -q`
Expected: `FileNotFoundError: … catalog-1.0.0.json`.

- [ ] **Step 2: Write the entry**

`agents/gdrive/catalog-1.0.0.json` (the logo is Google Drive's icon, Wikimedia Commons `Google_Drive_icon_(2020).svg`, 755 bytes, base64):

```json
{
  "format": 1,
  "id": "gdrive",
  "version": "1.0.0",
  "kind": "mcp",
  "service": {
    "image": "kaliper/agent-gdrive:1.0.0",
    "port": 8080,
    "timeout_seconds": 90,
    "memory_mb": 384
  },
  "needs_router": "0.4.0",
  "publisher": "Kaliper",
  "display": {
    "name": "Google Drive",
    "summary": "Searches and reads the files shared with your service account, at any folder depth: Google Docs, Sheets and Slides, PDFs, and Word, Excel and PowerPoint files.",
    "categories": ["Documents"],
    "logo": {
      "letter": "D",
      "color": "#1FA463",
      "image": "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgODcuMyA3OCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KCTxwYXRoIGQ9Im02LjYgNjYuODUgMy44NSA2LjY1Yy44IDEuNCAxLjk1IDIuNSAzLjMgMy4zbDEzLjc1LTIzLjhoLTI3LjVjMCAxLjU1LjQgMy4xIDEuMiA0LjV6IiBmaWxsPSIjMDA2NmRhIi8+Cgk8cGF0aCBkPSJtNDMuNjUgMjUtMTMuNzUtMjMuOGMtMS4zNS44LTIuNSAxLjktMy4zIDMuM2wtMjUuNCA0NGE5LjA2IDkuMDYgMCAwIDAgLTEuMiA0LjVoMjcuNXoiIGZpbGw9IiMwMGFjNDciLz4KCTxwYXRoIGQ9Im03My41NSA3Ni44YzEuMzUtLjggMi41LTEuOSAzLjMtMy4zbDEuNi0yLjc1IDcuNjUtMTMuMjVjLjgtMS40IDEuMi0yLjk1IDEuMi00LjVoLTI3LjUwMmw1Ljg1MiAxMS41eiIgZmlsbD0iI2VhNDMzNSIvPgoJPHBhdGggZD0ibTQzLjY1IDI1IDEzLjc1LTIzLjhjLTEuMzUtLjgtMi45LTEuMi00LjUtMS4yaC0xOC41Yy0xLjYgMC0zLjE1LjQ1LTQuNSAxLjJ6IiBmaWxsPSIjMDA4MzJkIi8+Cgk8cGF0aCBkPSJtNTkuOCA1M2gtMzIuM2wtMTMuNzUgMjMuOGMxLjM1LjggMi45IDEuMiA0LjUgMS4yaDUwLjhjMS42IDAgMy4xNS0uNDUgNC41LTEuMnoiIGZpbGw9IiMyNjg0ZmMiLz4KCTxwYXRoIGQ9Im03My40IDI2LjUtMTIuNy0yMmMtLjgtMS40LTEuOTUtMi41LTMuMy0zLjNsLTEzLjc1IDIzLjggMTYuMTUgMjhoMjcuNDVjMC0xLjU1LS40LTMuMS0xLjItNC41eiIgZmlsbD0iI2ZmYmEwMCIvPgo8L3N2Zz4="
    },
    "examples": [
      "What are the Q3 totals in the budget sheet?",
      "Summarise the latest board deck",
      "Which files mention the pricing change?"
    ]
  },
  "connection": {
    "method": "form",
    "fields": [
      {
        "key": "GOOGLE_SA_JSON",
        "label": "Service account key",
        "type": "file",
        "required": true,
        "help": "The JSON key file of a Google service account (the one Google Docs uses works too). Share the folders you want read with that account's email address. Its Google Cloud project needs the Google Drive API turned on."
      }
    ]
  },
  "router": {
    "source": "gdrive",
    "source_config": {},
    "agent": {
      "name": "gdrive",
      "source": "gdrive",
      "tools": ["browse_drive", "search_drive", "read_drive_file"],
      "description": "Searches and reads the files shared with the service account in Google Drive, at any folder depth: Google Docs, Sheets and Slides, PDFs, and Word, Excel and PowerPoint files -- specs, plans, proposals, budgets, trackers, meeting notes and decks that are not in the repository. A question naming a document without saying which system holds it may be here or in another document store: a filename does not say which, so ask every store.",
      "owns": "You own the files shared in Google Drive. Search first -- it reaches every file you can see, however deeply nested, and looks inside them -- and browse only to orient yourself. You do not own the source repository.\n\nEvery file and folder in a listing carries a link. When you report what a file says, GIVE THAT LINK with it: a Drive id is something you pass to read_drive_file, not something a reader can open.\n\nA file marked \"cannot be read\" exists: say so, and never guess what is in it from its name.",
      "holds_documents": true
    },
    "tool_descriptions": {
      "browse_drive": "List what is in Drive. Call with no folder_id to see what is shared with you, then call it again with a folder's id to see inside that folder. Files nested in subfolders are only visible by descending into them, so prefer search_drive when you know what you are looking for. Each file says what kind it is; one marked \"cannot be read\" exists, but its contents are not readable.",
      "search_drive": "Find files whose name or contents contain a word or phrase: Google Docs, Sheets and Slides, PDFs, and Word, Excel and PowerPoint files. This searches every file you can reach, however deeply nested, so it is the fastest way to locate material. Returns ids to pass to read_drive_file.",
      "read_drive_file": "Read the TEXT INSIDE one file, by the id shown by search_drive or browse_drive. Readable: Google Docs, Sheets and Slides; PDFs with selectable text; Word, Excel and PowerPoint; OpenDocument; CSV and plain text. A spreadsheet comes back one row per line with cells tab-separated, every sheet in turn. Not readable, and each says why rather than coming back empty: scanned PDFs, images, video, audio, forms, archives, old .doc/.xls/.ppt files, very large files, and files whose owner turned off downloading. When a file cannot be read, say it exists and its contents are not readable -- never guess them from its name."
    }
  }
}
```

`service.memory_mb` is 384 rather than the server default 256: a 25 MB workbook is unzipped and parsed in memory. It is a ceiling, not a reservation (idle agents measured 20-75 MiB).

- [ ] **Step 3: Run every check**

```bash
cd ~/Documents/agent-marketplace/agents/gdrive && uv run pytest -q         # expect 80 passed
cd ../.. && uv run pytest tests/test_entry.py -q                           # every entry valid, incl. gdrive/catalog-1.0.0.json
git status --short agents/gdocs agents/workdrive agents/kit                # expect nothing: untouched
docker build -f agents/gdrive/Dockerfile -t kaliper/agent-gdrive:1.0.0-check agents
docker run --rm -d --name gdrive-check -p 18080:8080 kaliper/agent-gdrive:1.0.0-check
sleep 3; curl -s -o /dev/null -w '%{http_code}\n' localhost:18080/health   # expect 503: no key set
docker rm -f gdrive-check
```

The 503 is right: `/health` answers 503 until every login is set.

- [ ] **Step 4: Commit**

```bash
git add agents/gdrive
git commit -m "gdrive 1.0.0: catalog entry for Google Drive"
```

---

### Task 7: Publish, and turn it on (Sahil runs the live steps)

**Files:**
- Create (by the publish script): `published/gdrive/1.0.0.json`

- [ ] **Step 1: Pull request into `main`**

```bash
git push -u origin feat/gdrive-agent
gh pr create --repo kaliperdev/agent-marketplace --base main --title "gdrive 1.0.0: Google Drive" \
  --body "A new catalog agent, Google Drive: searches and reads Google Docs, Sheets and Slides, PDFs and Office files shared with a service account (drive.readonly only). Google Docs, WorkDrive and the kit are unchanged. Why this design: docs/superpowers/plans/2026-10-14-google-drive-agent.md (Design). It replaces Google Docs on servers where it is turned on. Also carries notion 1.0.1's record (bb1b7f4). Tests: gdrive 80, every entry valid."
```

Merge once reviewed (`gh pr merge --merge`).

- [ ] **Step 2: Upload the package, then the entry**

```bash
agents/publish-image.sh gdrive 1.0.0                       # needs `docker login ghcr.io` with a token that can write packages
deploy/publish-to-hosted.sh agents/gdrive/catalog-1.0.0.json
git add published/gdrive/1.0.0.json && git commit -m "gdrive 1.0.0, as published" && git push
```

Expected: `deploy/publish-to-hosted.sh --list` shows `gdrive 1.0.0`.

- [ ] **Step 3: Add it on a server**

On a server's catalog page (Reva: https://revasure.rytangle.com/catalog/; Apprentice: https://kaliper.rytangle.com/catalog/), add **Google Drive** and upload the service-account key (the Google Docs key file works). Its container runs as `agent-gdrive` (Apprentice) or `reva-agent-gdrive` (Reva). Check `free -m` afterwards: each agent container uses about 65 MB more. Then **switch Google Docs off** on that server (the Design section's decision), so a question about a Google Doc is searched once.

- [ ] **Step 4: Live questions (Sahil runs these; each costs model calls)**

Share one test folder with the service account holding: a Google Sheet named "Drive test budget" with two tabs (Plan, Actual) holding Q3 figures, a Slides deck named "Drive test deck", a PDF with selectable text, and any video. Then ask in Slack:
1. "What are the Q3 figures in Drive test budget?" (answer from the first tab, with the link)
2. "What does the Actual tab of Drive test budget say for Q3?" (answer from the text, which holds every tab)
3. "Summarise Drive test deck"
4. "What does the PDF in the test folder say?"
5. "What is in the video in the test folder?" (says it exists and cannot be read; no guessed contents)
6. If the server's files are in a Shared Drive: add the service account to it, then ask about one of its files (confirms `corpora=allDrives` reaches it)
