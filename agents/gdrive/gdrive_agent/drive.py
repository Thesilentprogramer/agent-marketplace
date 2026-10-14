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
