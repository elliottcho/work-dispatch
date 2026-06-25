from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkItem:
    text: str
    workstream_id: str
    score: float = 0.0
    source_line: int | None = None


@dataclass
class Workstream:
    id: str
    name: str
    project_path: str
    keywords: list[str]
    chat_title: str
    agent_id: str | None
    asana_project_name: str | None
    asana_section: str | None
    granola_query: str | None = None
    granola_participants: list[str] = field(default_factory=list)


@dataclass
class RoutingPlan:
    date_label: str
    raw_notes: str
    items_by_workstream: dict[str, list[WorkItem]] = field(default_factory=dict)
    workstreams: dict[str, Workstream] = field(default_factory=dict)

    def summary(self) -> list[dict[str, Any]]:
        rows = []
        for ws_id, items in self.items_by_workstream.items():
            ws = self.workstreams.get(ws_id)
            rows.append(
                {
                    "workstream": ws.name if ws else ws_id,
                    "project": ws.project_path if ws else "",
                    "chat": ws.chat_title if ws else "",
                    "agent_id": ws.agent_id if ws else None,
                    "items": [i.text for i in items],
                }
            )
        return rows
