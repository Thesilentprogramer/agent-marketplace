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
