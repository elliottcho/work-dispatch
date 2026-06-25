from __future__ import annotations

import json
from pathlib import Path

from dispatch.asana_client import AsanaClient
from dispatch.cursor_client import CursorClient, try_sdk_send
from dispatch.granola import load_context
from dispatch.models import RoutingPlan
from dispatch.parser import format_briefing


def write_project_briefing(
    plan: RoutingPlan,
    workstream_id: str,
    template: str,
    *,
    include_granola: bool = False,
) -> Path:
    ws = plan.workstreams[workstream_id]
    project = Path(ws.project_path)
    docs = project / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    out = docs / f"kenneth-dispatch-{plan.date_label}.md"
    granola_ctx = load_context(workstream_id) if include_granola else None
    manager_ctx = load_context("_manager") if include_granola else None
    out.write_text(
        format_briefing(
            plan,
            workstream_id,
            template,
            granola_context=granola_ctx,
            manager_context=manager_ctx,
        )
    )
    return out


def execute_plan(
    plan: RoutingPlan,
    *,
    briefing_template: str,
    dry_run: bool = True,
    sync_asana: bool = False,
    include_granola: bool = False,
    asana_workspace_gid: str | None = None,
    cursor_api_key: str | None = None,
) -> list[dict]:
    results: list[dict] = []

    cursor: CursorClient | None = None
    asana: AsanaClient | None = None

    if not dry_run:
        try:
            cursor = CursorClient(api_key=cursor_api_key)
        except ValueError:
            pass
        if sync_asana:
            try:
                asana = AsanaClient()
            except ValueError as exc:
                results.append({"type": "asana_error", "message": str(exc)})

    for ws_id, items in plan.items_by_workstream.items():
        if not items:
            continue
        ws = plan.workstreams[ws_id]
        granola_ctx = load_context(ws_id) if include_granola else None
        manager_ctx = load_context("_manager") if include_granola else None
        briefing = format_briefing(
            plan,
            ws_id,
            briefing_template,
            granola_context=granola_ctx,
            manager_context=manager_ctx,
        )
        action = {
            "workstream": ws_id,
            "name": ws.name,
            "project_path": ws.project_path,
            "chat_title": ws.chat_title,
            "items": [i.text for i in items],
            "briefing_path": None,
            "granola_context_cached": bool(granola_ctx or manager_ctx),
            "cursor_action": None,
            "asana_task_gid": None,
        }

        if dry_run:
            action["cursor_action"] = "dry_run"
            results.append(action)
            continue

        briefing_path = write_project_briefing(
            plan, ws_id, briefing_template, include_granola=include_granola
        )
        action["briefing_path"] = str(briefing_path)

        if ws.agent_id:
            if ws.agent_id.startswith("bc-"):
                if cursor:
                    try:
                        run = cursor.send_followup(ws.agent_id, briefing)
                        action["cursor_action"] = {
                            "type": "cloud_followup",
                            "run_id": run.get("run", {}).get("id"),
                            "agent_url": f"https://cursor.com/agents/{ws.agent_id}",
                        }
                    except Exception as exc:  # noqa: BLE001
                        action["cursor_action"] = {"type": "error", "message": str(exc)}
                else:
                    action["cursor_action"] = {
                        "type": "manual",
                        "message": f"Set CURSOR_API_KEY and re-run, or open agent {ws.agent_id}",
                    }
            else:
                sdk_result = try_sdk_send(ws.agent_id, briefing, ws.project_path)
                if sdk_result:
                    action["cursor_action"] = {"type": "local_sdk", **sdk_result}
                else:
                    action["cursor_action"] = {
                        "type": "manual",
                        "message": (
                            f"Open Cursor chat titled '{ws.chat_title}' and paste briefing from "
                            f"{briefing_path}"
                        ),
                    }
        else:
            action["cursor_action"] = {
                "type": "new_chat",
                "message": (
                    f"Start a new Cursor chat in {ws.project_path} titled '{ws.chat_title}'. "
                    f"Briefing written to {briefing_path}. "
                    f"Then run: dispatch link-chat {ws_id} <agent-id>"
                ),
            }

        if sync_asana and asana and ws.asana_project_name and asana_workspace_gid:
            project = asana.find_project_by_name(asana_workspace_gid, ws.asana_project_name)
            if project:
                task_name = f"[Kenneth {plan.date_label}] {ws.name}"
                notes = briefing + f"\n\nBriefing file: {briefing_path}"
                gid = asana.create_task(
                    name=task_name,
                    notes=notes,
                    project_gid=project.gid,
                    due_on=plan.date_label if plan.date_label else None,
                )
                action["asana_task_gid"] = gid

        results.append(action)

    return results


def plan_to_json(plan: RoutingPlan) -> str:
    payload = {
        "date_label": plan.date_label,
        "summary": plan.summary(),
        "raw_notes": plan.raw_notes,
    }
    return json.dumps(payload, indent=2)
