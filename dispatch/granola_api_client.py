from __future__ import annotations

import os
from typing import Any, Iterator

import requests

API_BASE = "https://public-api.granola.ai/v1"


class GranolaApiClient:
    """Read-only client for Granola's public REST API (Business / Enterprise)."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("GRANOLA_API_KEY")
        if not key:
            raise ValueError(
                "GRANOLA_API_KEY is required for polling. "
                "Create one in Granola → Settings → Connectors → API keys."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        )

    def list_notes(
        self,
        *,
        updated_after: str | None = None,
        created_after: str | None = None,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if updated_after:
            params["updated_after"] = updated_after
        if created_after:
            params["created_after"] = created_after
        if cursor:
            params["cursor"] = cursor
        resp = self._session.get(f"{API_BASE}/notes", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_note(self, note_id: str, *, include_transcript: bool = False) -> dict[str, Any]:
        params = {"include": "transcript"} if include_transcript else None
        resp = self._session.get(f"{API_BASE}/notes/{note_id}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def iter_notes(
        self,
        *,
        updated_after: str | None = None,
        created_after: str | None = None,
        page_size: int = 50,
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            payload = self.list_notes(
                updated_after=updated_after,
                created_after=created_after,
                cursor=cursor,
                page_size=page_size,
            )
            for note in payload.get("notes", []):
                yield note
            if not payload.get("hasMore"):
                break
            cursor = payload.get("cursor")
            if not cursor:
                break
