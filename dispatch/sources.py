from __future__ import annotations

import re
from typing import Any


def source_label(meta: dict[str, Any], source_id: str | None = None) -> str:
    sources = meta.get("note_sources", {})
    if not source_id or source_id == "combined":
        manual = sources.get("manual", {}).get("label", "My notes from Kenneth")
        calls = sources.get("calls", {}).get("label", "Team calls")
        one_on_one = sources.get("one_on_one", {}).get("label", "1:1 meetings")
        return f"{manual} + {calls} + {one_on_one} (Granola)"
    entry = sources.get(source_id, {})
    return entry.get("label", source_id.replace("_", " "))


def _participant_names(note: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("attendees", "participants"):
        for entry in note.get(key) or []:
            if isinstance(entry, str):
                names.add(entry.strip().lower())
            elif isinstance(entry, dict):
                for field in ("name", "display_name", "email"):
                    val = entry.get(field)
                    if val:
                        names.add(str(val).strip().lower())
                        break
    return names


def classify_granola_note(note: dict[str, Any], meta: dict[str, Any]) -> str:
    """Return note_sources key: one_on_one, calls, or calls (default)."""
    title = (note.get("title") or "").lower()
    sources = meta.get("note_sources", {})
    manager = meta.get("manager", "Kenneth").lower()

    for kind in ("one_on_one", "calls"):
        cfg = sources.get(kind, {}).get("granola", {})
        patterns = cfg.get("title_patterns") or []
        if not patterns:
            continue
        if not any(p.lower() in title or re.search(re.escape(p), title, re.I) for p in patterns):
            continue
        if cfg.get("require_manager"):
            blob = title + " " + (note.get("summary") or "").lower()
            if manager not in blob and manager not in _participant_names(note):
                continue
        return kind
    return "calls"
