from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from dispatch.models import Workstream


def _expand(path: str) -> str:
    return str(Path(path).expanduser())


def load_registry(path: Path | None = None) -> tuple[list[Workstream], dict[str, Any]]:
    registry_path = path or Path(__file__).resolve().parent / "registry.yaml"
    with registry_path.open() as f:
        data = yaml.safe_load(f)

    workstreams: list[Workstream] = []
    for entry in data.get("workstreams", []):
        chat = entry.get("chat", {})
        asana = entry.get("asana", {})
        granola = entry.get("granola", {})
        workstreams.append(
            Workstream(
                id=entry["id"],
                name=entry["name"],
                project_path=_expand(entry["project_path"]),
                keywords=[k.lower() for k in entry.get("keywords", [])],
                chat_title=chat.get("title", entry["name"]),
                agent_id=chat.get("agent_id"),
                asana_project_name=asana.get("project_name"),
                asana_section=asana.get("section"),
                granola_query=granola.get("query"),
                granola_participants=granola.get("participants") or [],
                integrations=entry.get("integrations"),
            )
        )

    routing = data.get("routing", {})
    meta = {
        "manager": data.get("manager", "Manager"),
        "fallback_workstream": routing.get("fallback_workstream", "general"),
        "min_match_score": float(routing.get("min_match_score", 0.15)),
        "briefing_template": data.get("briefing_template", ""),
        "granola": data.get("granola", {}),
        "automation": data.get("automation", {}),
        "integrations": data.get("integrations", {}),
        "note_sources": data.get("note_sources", {}),
    }
    return workstreams, meta


CHAT_TITLE_CODES: dict[str, str] = {
    "hk-vetting": "HK",
    "pro-activation": "PRO",
    "general": "WD",
}

CHAT_TITLE_LABELS: dict[str, str] = {
    "hk-vetting": "Lisle",
    "pro-activation": "Aris",
    "general": "Route",
}


def standard_chat_title(workstream_id: str, short_label: str | None = None) -> str:
    """Short prefix-first titles — unique and readable in the first 10 chars."""
    code = CHAT_TITLE_CODES.get(workstream_id, workstream_id[:3])
    label = short_label or CHAT_TITLE_LABELS.get(workstream_id, workstream_id)
    return f"{code} · {label}"


def _save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    registry_path = path or Path(__file__).resolve().parent / "registry.yaml"
    with registry_path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def save_agent_id(workstream_id: str, agent_id: str, path: Path | None = None) -> None:
    registry_path = path or Path(__file__).resolve().parent / "registry.yaml"
    with registry_path.open() as f:
        data = yaml.safe_load(f)

    for entry in data.get("workstreams", []):
        if entry["id"] == workstream_id:
            entry.setdefault("chat", {})["agent_id"] = agent_id
            break
    else:
        raise KeyError(f"Unknown workstream: {workstream_id}")

    _save_registry(data, path)


def save_chat_title(workstream_id: str, title: str, path: Path | None = None) -> None:
    registry_path = path or Path(__file__).resolve().parent / "registry.yaml"
    with registry_path.open() as f:
        data = yaml.safe_load(f)

    for entry in data.get("workstreams", []):
        if entry["id"] == workstream_id:
            entry.setdefault("chat", {})["title"] = title
            break
    else:
        raise KeyError(f"Unknown workstream: {workstream_id}")

    _save_registry(data, path)


def apply_standard_chat_titles(path: Path | None = None) -> list[dict[str, str]]:
    registry_path = path or Path(__file__).resolve().parent / "registry.yaml"
    with registry_path.open() as f:
        data = yaml.safe_load(f)

    rows: list[dict[str, str]] = []
    for entry in data.get("workstreams", []):
        ws_id = entry["id"]
        title = standard_chat_title(ws_id)
        chat = entry.setdefault("chat", {})
        chat["title"] = title
        rows.append(
            {
                "workstream": ws_id,
                "title": title,
                "agent_id": chat.get("agent_id") or "",
                "project": _expand(entry["project_path"]),
            }
        )

    _save_registry(data, path)
    return rows
