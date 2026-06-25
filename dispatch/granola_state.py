from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "granola-state.json"


@dataclass
class GranolaState:
    last_poll_at: str | None = None
    processed_note_ids: list[str] = field(default_factory=list)
    last_run_results: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> GranolaState:
        path = path or STATE_PATH
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(
            last_poll_at=data.get("last_poll_at"),
            processed_note_ids=list(data.get("processed_note_ids", [])),
            last_run_results=list(data.get("last_run_results", [])),
        )

    def save(self, path: Path | None = None) -> None:
        path = path or STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "last_poll_at": self.last_poll_at,
                    "processed_note_ids": self.processed_note_ids,
                    "last_run_results": self.last_run_results[-20:],
                },
                indent=2,
            )
            + "\n"
        )

    def is_processed(self, note_id: str) -> bool:
        return note_id in self.processed_note_ids

    def mark_processed(self, note_id: str) -> None:
        if note_id not in self.processed_note_ids:
            self.processed_note_ids.append(note_id)

    def touch_poll(self) -> str:
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        return self.last_poll_at
