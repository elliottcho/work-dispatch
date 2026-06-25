from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dispatch.models import RoutingPlan, Workstream

CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "integration-context"

SOURCES = ("confluence", "redshift", "mode", "replit", "finch")


def context_path(workstream_id: str, source: str) -> Path:
    return CACHE_ROOT / workstream_id / f"{source}.md"


def load_integration_context(workstream_id: str, source: str) -> str | None:
    path = context_path(workstream_id, source)
    if not path.exists():
        return None
    text = path.read_text().strip()
    return text or None


def save_integration_context(workstream_id: str, source: str, content: str) -> Path:
    path = context_path(workstream_id, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"<!-- saved: {datetime.now(timezone.utc).isoformat()} source: {source} -->\n\n"
    path.write_text(header + content.strip() + "\n")
    return path


def merge_integration_block(workstream_id: str, enabled_sources: list[str]) -> str:
    parts: list[str] = []
    labels = {
        "confluence": "Confluence (Pantry)",
        "redshift": "Redshift (Finch)",
        "mode": "Mode",
        "replit": "Replit",
        "finch": "Finch",
    }
    for source in enabled_sources:
        ctx = load_integration_context(workstream_id, source)
        if ctx:
            parts.append(f"### {labels.get(source, source)}\n\n{ctx}")
    shared = load_integration_context("_shared", "mode")
    if shared and "mode" in enabled_sources and workstream_id != "_shared":
        if not any("### Mode" in p for p in parts):
            parts.append(f"### Mode (shared)\n\n{shared}")
    return "\n\n".join(parts) if parts else "_No integration context cached yet — run integration-queries in Dispatch chat._"


def build_integration_queries(
    workstreams: list[Workstream],
    meta: dict[str, Any],
    plan: RoutingPlan | None = None,
) -> dict[str, Any]:
    integrations = meta.get("integrations", {})
    if not integrations.get("enabled", True):
        return {"enabled": False, "queries": []}

    confluence = integrations.get("confluence", {})
    space_key = confluence.get("space_key", "PANTRY")
    active_ids = set(plan.items_by_workstream.keys()) if plan else {ws.id for ws in workstreams}
    queries: list[dict[str, Any]] = []

    for ws in workstreams:
        if ws.id not in active_ids:
            continue
        ws_int = ws.integrations or {}

        cql = ws_int.get("confluence_cql") or (
            f'space = {space_key} AND text ~ "{ws.name}" ORDER BY lastmodified DESC'
        )
        queries.append(
            {
                "workstream": ws.id,
                "stage": "confluence",
                "mcp_server": "atlassian",
                "tools": ["searchConfluenceUsingCql", "getConfluencePage"],
                "args_hint": {"cql": cql, "limit": 5},
                "save_to": str(context_path(ws.id, "confluence")),
            }
        )

        redshift_hint = ws_int.get("redshift_hint") or f"Metrics and counts for: {ws.name}"
        queries.append(
            {
                "workstream": ws.id,
                "stage": "redshift",
                "mcp_server": "finch-redshift",
                "tools": ["list_tables", "list_columns", "execute_query"],
                "query": redshift_hint,
                "save_to": str(context_path(ws.id, "redshift")),
            }
        )

        mode_reports = ws_int.get("mode_reports") or [ws.name]
        queries.append(
            {
                "workstream": ws.id,
                "stage": "mode",
                "mcp_server": "mode-analytics",
                "tools": ["list_reports", "get_report", "run_query"],
                "reports": mode_reports,
                "save_to": str(context_path(ws.id, "mode")),
            }
        )

        if ws_int.get("replit_when_needed", integrations.get("replit", {}).get("default_optional", True)):
            queries.append(
                {
                    "workstream": ws.id,
                    "stage": "replit",
                    "mcp_server": "replit",
                    "optional": True,
                    "hint": ws_int.get("replit_hint") or f"Prototype or spike for: {ws.name}",
                    "save_to": str(context_path(ws.id, "replit")),
                }
            )

    return {
        "enabled": True,
        "confluence_space": space_key,
        "queries": queries,
        "save_commands": {
            "example": "dispatch save-integration-context <workstream> <source> /tmp/context.md",
            "sources": list(SOURCES),
        },
    }
