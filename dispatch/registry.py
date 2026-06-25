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

    with registry_path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
