from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dispatch.models import RoutingPlan, Workstream

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "granola-context"


def context_path(workstream_id: str) -> Path:
    return CACHE_DIR / f"{workstream_id}.md"


def load_context(workstream_id: str) -> str | None:
    path = context_path(workstream_id)
    if not path.exists():
        return None
    text = path.read_text().strip()
    return text or None


def save_context(workstream_id: str, content: str, *, source: str = "granola") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    header = f"<!-- saved: {datetime.now(timezone.utc).isoformat()} source: {source} -->\n\n"
    path = context_path(workstream_id)
    path.write_text(header + content.strip() + "\n")
    return path


def build_granola_queries(
    workstreams: list[Workstream],
    meta: dict[str, Any],
    plan: RoutingPlan | None = None,
) -> list[dict[str, Any]]:
    granola = meta.get("granola", {})
    manager = meta.get("manager", "Manager")
    queries: list[dict[str, Any]] = []

    manager_query = granola.get(
        "manager_query",
        f"What did {manager} say about priorities, goals, and action items recently?",
    )
    queries.append(
        {
            "id": "manager-priorities",
            "workstream": None,
            "tool": "query_granola_meetings",
            "query": manager_query,
            "also": [
                {
                    "tool": "list_meetings",
                    "hint": f"Meetings with {manager} in the last {granola.get('lookback_days', 14)} days",
                }
            ],
        }
    )

    active_ids = set(plan.items_by_workstream.keys()) if plan else {ws.id for ws in workstreams}
    for ws in workstreams:
        if ws.id not in active_ids:
            continue
        query = ws.granola_query or f"{ws.name}: recent decisions, action items, and blockers"
        entry: dict[str, Any] = {
            "id": ws.id,
            "workstream": ws.id,
            "tool": "query_granola_meetings",
            "query": query,
            "save_to": str(context_path(ws.id)),
        }
        if ws.granola_participants:
            entry["participants"] = ws.granola_participants
            entry["also"] = [
                {
                    "tool": "list_meetings",
                    "hint": f"Meetings involving {', '.join(ws.granola_participants)}",
                }
            ]
        queries.append(entry)

    return queries


def merge_contexts_for_plan(plan: RoutingPlan, enabled: bool) -> dict[str, str]:
    if not enabled:
        return {}
    contexts: dict[str, str] = {}
    for ws_id in plan.items_by_workstream:
        ctx = load_context(ws_id)
        if ctx:
            contexts[ws_id] = ctx
    manager_ctx = load_context("_manager")
    if manager_ctx:
        contexts["_manager"] = manager_ctx
    return contexts
