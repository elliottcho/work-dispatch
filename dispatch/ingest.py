from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dispatch.executor import execute_plan, plan_to_json
from dispatch.flowchart import emit_flowchart
from dispatch.granola import save_context
from dispatch.granola_api_client import GranolaApiClient
from dispatch.granola_state import GranolaState
from dispatch.models import Workstream
from dispatch.parser import parse_notes
from dispatch.sources import classify_granola_note, source_label

ROOT = Path(__file__).resolve().parent.parent


def _automation_config(meta: dict[str, Any]) -> dict[str, Any]:
    auto = meta.get("automation", {})
    filters = auto.get("filters", {})
    on_new = auto.get("on_new_note", {})
    manager = meta.get("manager", "Kenneth")
    title_keywords = filters.get("title_keywords") or []
    title_patterns = [re.escape(k) for k in title_keywords] if title_keywords else []
    return {
        "enabled": auto.get("enabled", True),
        "state_file": auto.get("state_file", "data/granola-state.json"),
        "ingest_dir": auto.get("ingest_dir", "data/granola-ingest"),
        "manager_participants": [manager],
        "participants_any": filters.get("participants_any") or [],
        "title_patterns": title_patterns,
        "require_manager": filters.get("require_manager", True),
        "min_action_items": int(filters.get("min_action_items", 0)),
        "initial_lookback_hours": int(auto.get("granola_api", {}).get("initial_lookback_hours", 24)),
        "on_ingest": {
            "dry_run": on_new.get("dry_run", False),
            "include_granola": on_new.get("include_granola", True),
            "sync_asana": on_new.get("push_asana", False),
            "cache_context": on_new.get("cache_context", True),
            "push_cursor": on_new.get("push_cursor", True),
        },
    }


def _state_path(meta: dict[str, Any]) -> Path:
    rel = _automation_config(meta).get("state_file", "data/granola-state.json")
    return ROOT / rel


def _ingest_dir(meta: dict[str, Any]) -> Path:
    rel = _automation_config(meta).get("ingest_dir", "data/granola-ingest")
    return ROOT / rel


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _participant_names(note: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("attendees", "participants"):
        for entry in note.get(key) or []:
            if isinstance(entry, str):
                names.add(_normalize_name(entry))
            elif isinstance(entry, dict):
                for field in ("name", "display_name", "email"):
                    val = entry.get(field)
                    if val:
                        names.add(_normalize_name(str(val)))
                        break
    calendar = note.get("calendar_event") or {}
    for entry in calendar.get("attendees") or []:
        if isinstance(entry, dict):
            val = entry.get("name") or entry.get("email")
            if val:
                names.add(_normalize_name(str(val)))
    return names


def _text_mentions_manager(note: dict[str, Any], manager_names: set[str]) -> bool:
    blob = " ".join(
        str(note.get(k) or "")
        for k in ("title", "summary", "summary_markdown")
    ).lower()
    return any(name in blob for name in manager_names)


def note_matches_trigger(note: dict[str, Any], automation: dict[str, Any]) -> bool:
    title = (note.get("title") or "").lower()
    patterns = automation.get("title_patterns") or []
    title_hit = any(re.search(pat, title, re.I) for pat in patterns) if patterns else True

    manager_names = {_normalize_name(n) for n in automation.get("manager_participants") or []}
    participants = _participant_names(note)
    if automation.get("require_manager"):
        manager_hit = bool(manager_names & participants) or _text_mentions_manager(note, manager_names)
    else:
        manager_hit = True

    extra = automation.get("participants_any") or []
    if extra:
        wanted = {_normalize_name(p) for p in extra}
        if not (participants & wanted):
            return False

    action_items = note.get("action_items") or note.get("actions") or []
    min_items = automation.get("min_action_items", 0)
    if min_items and len(action_items) < min_items:
        return False

    return title_hit and manager_hit


def _priority_lines_from_markdown(text: str) -> str:
    """Prefer bullet lists under a Priorities/Action items heading for routing."""
    lines = text.splitlines()
    collected: list[str] = []
    in_section = False
    for raw in lines:
        line = raw.strip()
        lower = line.lower()
        if re.match(r"^#+\s*(priorities|action items)", lower):
            in_section = True
            continue
        if in_section and re.match(r"^#+\s", line):
            break
        if in_section and re.match(r"^[-*•]\s+", line):
            collected.append(re.sub(r"^[-*•]\s+", "", line))
        elif in_section and re.match(r"^\[[ x]\]\s+", line, re.I):
            collected.append(re.sub(r"^\[[ x]\]\s+", "", line, flags=re.I))
    if collected:
        return "\n".join(f"- {item}" for item in collected)
    return text


def extract_dispatch_text(note: dict[str, Any]) -> str:
    parts: list[str] = []
    title = (note.get("title") or "").strip()
    if title and not str(note.get("id", "")).startswith("file_"):
        parts.append(title)

    summary = (note.get("summary_markdown") or note.get("summary") or "").strip()
    if summary:
        summary = _priority_lines_from_markdown(summary)
        parts.append(summary)

    action_items = note.get("action_items") or note.get("actions") or []
    if action_items:
        bullets: list[str] = []
        for item in action_items:
            if isinstance(item, str):
                bullets.append(f"- {item.strip()}")
            elif isinstance(item, dict):
                text = item.get("text") or item.get("title") or item.get("description")
                assignee = item.get("assignee") or item.get("owner")
                if text:
                    line = str(text).strip()
                    if assignee:
                        line += f" ({assignee})"
                    bullets.append(f"- {line}")
        if bullets:
            parts.append("Action items:\n" + "\n".join(bullets))

    if not parts:
        raise ValueError(f"Note {note.get('id')} has no extractable summary or action items")

    return "\n\n".join(parts)


def save_ingest_artifact(note: dict[str, Any], notes_text: str, meta: dict[str, Any]) -> Path:
    ingest_dir = _ingest_dir(meta)
    ingest_dir.mkdir(parents=True, exist_ok=True)
    note_id = note.get("id") or "unknown"
    safe_id = re.sub(r"[^\w-]", "_", note_id)
    path = ingest_dir / f"{safe_id}.json"
    payload = {
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "note_id": note_id,
        "title": note.get("title"),
        "created_at": note.get("created_at"),
        "updated_at": note.get("updated_at"),
        "participants": sorted(_participant_names(note)),
        "dispatch_text": notes_text,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def build_manager_context(note: dict[str, Any], notes_text: str) -> str:
    title = note.get("title") or "Granola note"
    created = note.get("created_at") or note.get("updated_at") or ""
    header = f"### {title}"
    if created:
        header += f" ({created[:10]})"
    return f"{header}\n\n{notes_text.strip()}"


def _note_summary(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": note.get("id"),
        "title": note.get("title"),
        "created_at": note.get("created_at"),
        "updated_at": note.get("updated_at"),
        "participants": sorted(_participant_names(note)),
    }


def poll_granola(
    workstreams: list[Workstream] | None = None,
    meta: dict[str, Any] | None = None,
    *,
    api_key: str | None = None,
    dry_run: bool = True,
    sync_asana: bool = False,
    include_granola: bool = True,
    force_note_ids: list[str] | None = None,
    search: str | None = None,
    include_processed: bool = False,
    asana_workspace_gid: str | None = None,
    cursor_api_key: str | None = None,
    granola_api_key: str | None = None,
) -> dict[str, Any]:
    """Detect new Granola notes; optionally ingest them."""
    if workstreams is None or meta is None:
        workstreams, meta = load_registry()

    automation = _automation_config(meta)
    state = GranolaState.load(_state_path(meta))
    key = granola_api_key or api_key

    result: dict[str, Any] = {
        "status": "ok",
        "last_poll_at": state.last_poll_at,
        "candidates": [],
        "skipped_processed": [],
        "ingested": [],
        "errors": [],
    }

    if not automation.get("enabled", True):
        result["status"] = "disabled"
        return result

    candidates: list[dict[str, Any]] = []

    try:
        client = GranolaApiClient(api_key=key)
    except ValueError as exc:
        result["errors"].append({"error": str(exc)})
        result["status"] = "error"
        return result

    if force_note_ids:
        for nid in force_note_ids:
            try:
                candidates.append(client.get_note(nid))
            except Exception as exc:  # noqa: BLE001
                result["errors"].append({"note_id": nid, "error": str(exc)})
    elif search:
        pattern = re.compile(search, re.I)
        for note in client.iter_notes(page_size=30):
            if not pattern.search(note.get("title") or ""):
                continue
            if not include_processed and state.is_processed(note["id"]):
                result["skipped_processed"].append(note["id"])
                continue
            candidates.append(note)
    else:
        created_after: str | None = None
        updated_after: str | None = state.last_poll_at
        if not updated_after:
            hours = automation.get("initial_lookback_hours", 24)
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            created_after = since.replace(microsecond=0).isoformat()

        for note in client.iter_notes(
            updated_after=updated_after,
            created_after=created_after,
            page_size=30,
        ):
            note_id = note.get("id")
            if not note_id:
                continue
            if not include_processed and state.is_processed(note_id):
                result["skipped_processed"].append(note_id)
                continue
            if note_matches_trigger(note, automation):
                candidates.append(note)

        if not dry_run:
            state.touch_poll()
            state.save(_state_path(meta))
        result["last_poll_at"] = state.last_poll_at

    result["candidates"] = [_note_summary(n) for n in candidates]

    if dry_run and not force_note_ids and not search:
        return result

    for note in candidates:
        try:
            ingested = ingest_note(
                note,
                workstreams,
                meta,
                dry_run=dry_run,
                sync_asana=sync_asana,
                include_granola=include_granola,
                cache_context=automation["on_ingest"].get("cache_context", True),
                asana_workspace_gid=asana_workspace_gid,
                cursor_api_key=cursor_api_key,
                granola_api_key=key,
                fetch_full=not note.get("summary") and not note.get("summary_markdown"),
            )
            result["ingested"].append(ingested)
        except Exception as exc:  # noqa: BLE001
            result["errors"].append({"note_id": note.get("id"), "error": str(exc)})

    return result


def ingest_note(
    note: dict[str, Any],
    workstreams: list[Workstream],
    meta: dict[str, Any],
    *,
    dry_run: bool = True,
    sync_asana: bool = False,
    include_granola: bool = True,
    cache_context: bool = True,
    date_label: str | None = None,
    source: str = "granola-api",
    asana_workspace_gid: str | None = None,
    cursor_api_key: str | None = None,
    granola_api_key: str | None = None,
    fetch_full: bool = True,
) -> dict[str, Any]:
    state = GranolaState.load(_state_path(meta))
    note_id = note.get("id")

    if fetch_full and note_id and str(note_id).startswith("not_"):
        if not note.get("summary") and not note.get("summary_markdown"):
            client = GranolaApiClient(api_key=granola_api_key)
            note = client.get_note(note_id)

    notes_text = extract_dispatch_text(note)
    artifact_path = None
    if not dry_run:
        artifact_path = save_ingest_artifact(note, notes_text, meta)

    manager_path = None
    if cache_context and not dry_run:
        manager_ctx = build_manager_context(note, notes_text)
        manager_path = save_context("_manager", manager_ctx, source=source)
        for ws in workstreams:
            if ws.granola_participants and _participant_names(note) & {
                _normalize_name(p) for p in ws.granola_participants
            }:
                save_context(ws.id, manager_ctx, source=source)

    plan = parse_notes(
        notes_text,
        workstreams,
        fallback_id=meta["fallback_workstream"],
        min_match_score=meta["min_match_score"],
        date_label=date_label or date.today().isoformat(),
    )

    flowchart = emit_flowchart(meta, command="ingest", plan_summary=plan.summary())

    granola_kind = classify_granola_note(note, meta)
    note_src = source_label(meta, granola_kind)

    int_cfg = meta.get("integrations", {})
    push_results = execute_plan(
        plan,
        briefing_template=meta["briefing_template"],
        dry_run=dry_run,
        sync_asana=sync_asana,
        include_granola=include_granola,
        include_integrations=int_cfg.get("enabled", True),
        integration_sources=int_cfg.get("sources", ["confluence", "redshift", "mode"]),
        note_source=note_src,
        asana_workspace_gid=asana_workspace_gid or os.environ.get("ASANA_WORKSPACE_GID"),
        cursor_api_key=cursor_api_key or os.environ.get("CURSOR_API_KEY"),
    )

    if note_id and not dry_run:
        state.mark_processed(note_id)
    if not dry_run:
        state.last_run_results.append(
            {
                "note_id": note_id,
                "title": note.get("title"),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "artifact": str(artifact_path) if artifact_path else None,
                "dry_run": dry_run,
                "workstreams": list(plan.items_by_workstream.keys()),
            }
        )
        state.save(_state_path(meta))

    return {
        "note": _note_summary(note),
        "artifact_path": str(artifact_path) if artifact_path else None,
        "manager_context_path": str(manager_path) if manager_path else None,
        "flowchart_path": flowchart.get("flowchart_path"),
        "note_source": note_src,
        "granola_note_kind": granola_kind,
        "dispatch_text": notes_text,
        "plan": json.loads(plan_to_json(plan)),
        "push_results": push_results,
        "dry_run": dry_run,
    }


def ingest_text(
    notes: str,
    workstreams: list[Workstream],
    meta: dict[str, Any],
    *,
    source: str = "manual",
    dry_run: bool = True,
    sync_asana: bool = False,
    include_granola: bool = True,
    cache_context: bool = True,
    date_label: str | None = None,
    asana_workspace_gid: str | None = None,
    cursor_api_key: str | None = None,
) -> dict[str, Any]:
    note = {
        "id": f"manual_{date.today().isoformat()}",
        "title": f"Manual ingest ({source})",
        "summary_markdown": notes,
    }
    return ingest_note(
        note,
        workstreams,
        meta,
        dry_run=dry_run,
        sync_asana=sync_asana,
        include_granola=include_granola,
        cache_context=cache_context,
        date_label=date_label,
        source=source,
        asana_workspace_gid=asana_workspace_gid,
        cursor_api_key=cursor_api_key,
        fetch_full=False,
    )


def ingest_webhook_payload(
    payload: dict[str, Any],
    workstreams: list[Workstream],
    meta: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Accept a future Zapier/custom webhook shape; today Granola has no native webhooks."""
    note = payload.get("note") or payload
    if "summary" not in note and "summary_markdown" not in note:
        text = payload.get("text") or payload.get("body") or payload.get("notes")
        if text:
            note = {"id": payload.get("id", "webhook"), "title": payload.get("title", "Webhook"), "summary_markdown": text}
    return ingest_note(note, workstreams, meta, source="webhook", **kwargs)


def ingest_granola(
    *,
    note_id: str | None = None,
    search: str | None = None,
    file_path: Path | None = None,
    dry_run: bool | None = None,
    include_granola: bool | None = None,
    sync_asana: bool = False,
    date_label: str | None = None,
    granola_api_key: str | None = None,
) -> dict[str, Any]:
    workstreams, meta = load_registry()
    automation = _automation_config(meta)
    on = automation["on_ingest"]
    if dry_run is None:
        dry_run = bool(on.get("dry_run", False))
    if include_granola is None:
        include_granola = bool(on.get("include_granola", True))

    if file_path:
        text = file_path.read_text().strip()
        title = file_path.stem.replace("-", " ").replace("_", " ")
        note = {
            "id": f"file_{file_path.stem}",
            "title": title,
            "summary_markdown": text,
            "attendees": [{"name": meta.get("manager", "Kenneth")}],
        }
        return {
            "mode": "file",
            "ingested": [
                ingest_note(
                    note,
                    workstreams,
                    meta,
                    dry_run=dry_run,
                    sync_asana=sync_asana,
                    include_granola=include_granola,
                    date_label=date_label,
                    source=f"file:{file_path.name}",
                    fetch_full=False,
                )
            ],
        }

    report = poll_granola(
        workstreams,
        meta,
        dry_run=dry_run,
        sync_asana=sync_asana,
        include_granola=include_granola,
        force_note_ids=[note_id] if note_id else None,
        search=search,
        include_processed=bool(note_id or search),
        granola_api_key=granola_api_key,
    )
    return {
        "mode": "targeted" if (note_id or search) else "poll",
        "poll": report,
        "ingested": report.get("ingested", []),
        "errors": report.get("errors", []),
    }
