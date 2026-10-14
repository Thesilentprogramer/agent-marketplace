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
