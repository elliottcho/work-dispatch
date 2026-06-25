from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from dispatch.executor import execute_plan, plan_to_json
from dispatch.granola import build_granola_queries, save_context
from dispatch.ingest import ingest_granola, ingest_text, ingest_webhook_payload, poll_granola
from dispatch.parser import parse_notes
from dispatch.registry import load_registry, save_agent_id
from dispatch.cursor_client import CursorClient


def _load_notes(args: argparse.Namespace) -> str:
    if args.notes:
        return args.notes
    if args.file:
        return Path(args.file).read_text()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide notes via --notes, --file, or stdin")


def _granola_enabled(args: argparse.Namespace, meta: dict) -> bool:
    if getattr(args, "no_granola", False):
        return False
    if getattr(args, "granola", False):
        return True
    return bool(meta.get("granola", {}).get("enabled", False))


def _automation_flags(args: argparse.Namespace, meta: dict) -> tuple[bool, bool, bool]:
    """Resolve dry_run, sync_asana, include_granola from CLI + registry automation.on_new_note."""
    on_new = meta.get("automation", {}).get("on_new_note", {})
    if getattr(args, "execute", False):
        dry_run = False
    elif args.dry_run:
        dry_run = True
    else:
        dry_run = bool(on_new.get("dry_run", False))
    sync_asana = (args.asana or on_new.get("push_asana", False)) and not dry_run
    include_granola = not getattr(args, "no_granola", False) and (
        getattr(args, "granola", False)
        or on_new.get("include_granola", meta.get("granola", {}).get("enabled", False))
    )
    return dry_run, sync_asana, include_granola


def cmd_plan(args: argparse.Namespace) -> int:
    load_dotenv()
    workstreams, meta = load_registry()
    notes = _load_notes(args)
    plan = parse_notes(
        notes,
        workstreams,
        fallback_id=meta["fallback_workstream"],
        min_match_score=meta["min_match_score"],
        date_label=args.date,
    )
    print(plan_to_json(plan))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv()
    workstreams, meta = load_registry()
    notes = _load_notes(args)
    plan = parse_notes(
        notes,
        workstreams,
        fallback_id=meta["fallback_workstream"],
        min_match_score=meta["min_match_score"],
        date_label=args.date,
    )
    results = execute_plan(
        plan,
        briefing_template=meta["briefing_template"],
        dry_run=args.dry_run,
        sync_asana=args.asana and not args.dry_run,
        include_granola=_granola_enabled(args, meta),
        asana_workspace_gid=os.environ.get("ASANA_WORKSPACE_GID"),
        cursor_api_key=os.environ.get("CURSOR_API_KEY"),
    )
    print(json.dumps(results, indent=2))
    return 0


def cmd_list_chats(args: argparse.Namespace) -> int:
    load_dotenv()
    client = CursorClient()
    agents = client.list_agents(limit=args.limit)
    for agent in agents:
        print(f"{agent.id}\t{agent.status}\t{agent.name}\t{agent.url or ''}")
    return 0


def cmd_granola_queries(args: argparse.Namespace) -> int:
    load_dotenv()
    workstreams, meta = load_registry()
    plan = None
    if args.notes or args.file or not sys.stdin.isatty():
        notes = _load_notes(args)
        plan = parse_notes(
            notes,
            workstreams,
            fallback_id=meta["fallback_workstream"],
            min_match_score=meta["min_match_score"],
            date_label=args.date,
        )
    queries = build_granola_queries(workstreams, meta, plan)
    print(json.dumps({"granola_enabled": meta.get("granola", {}).get("enabled", False), "queries": queries}, indent=2))
    return 0


def cmd_save_granola_context(args: argparse.Namespace) -> int:
    content = Path(args.file).read_text()
    path = save_context(args.workstream, content, source=args.source)
    print(f"Saved Granola context → {path}")
    return 0


def cmd_poll_granola(args: argparse.Namespace) -> int:
    load_dotenv()
    workstreams, meta = load_registry()
    dry_run, sync_asana, include_granola = _automation_flags(args, meta)
    force_ids = args.note_id or None
    report = poll_granola(
        workstreams,
        meta,
        dry_run=dry_run,
        sync_asana=sync_asana,
        include_granola=include_granola,
        force_note_ids=force_ids,
        search=args.search,
        include_processed=args.include_processed,
        asana_workspace_gid=os.environ.get("ASANA_WORKSPACE_GID"),
        cursor_api_key=os.environ.get("CURSOR_API_KEY"),
        granola_api_key=os.environ.get("GRANOLA_API_KEY"),
    )
    print(json.dumps(report, indent=2))
    return 0 if not report.get("errors") else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    load_dotenv()
    workstreams, meta = load_registry()
    dry_run, sync_asana, include_granola = _automation_flags(args, meta)

    if args.webhook:
        payload = json.loads(Path(args.webhook).read_text())
        result = ingest_webhook_payload(
            payload,
            workstreams,
            meta,
            dry_run=dry_run,
            sync_asana=sync_asana,
            include_granola=include_granola,
            asana_workspace_gid=os.environ.get("ASANA_WORKSPACE_GID"),
            cursor_api_key=os.environ.get("CURSOR_API_KEY"),
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.note_id or args.search or args.file:
        file_path = Path(args.file) if args.file else None
        result = ingest_granola(
            note_id=args.note_id,
            search=args.search,
            file_path=file_path,
            dry_run=dry_run,
            include_granola=include_granola,
            sync_asana=sync_asana,
            date_label=args.date,
            granola_api_key=os.environ.get("GRANOLA_API_KEY"),
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ingested") or not result.get("errors") else 1

    notes = _load_notes(args)
    result = ingest_text(
        notes,
        workstreams,
        meta,
        source=args.source,
        dry_run=dry_run,
        sync_asana=sync_asana,
        include_granola=include_granola,
        cache_context=not args.no_cache_context,
        date_label=args.date,
        asana_workspace_gid=os.environ.get("ASANA_WORKSPACE_GID"),
        cursor_api_key=os.environ.get("CURSOR_API_KEY"),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_link_chat(args: argparse.Namespace) -> int:
    save_agent_id(args.workstream, args.agent_id)
    print(f"Linked {args.workstream} → {args.agent_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Route Kenneth's priorities into Cursor chats and Asana"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan", help="Parse notes and show routing plan (JSON)")
    plan_p.add_argument("--notes", "-n", help="Notes text")
    plan_p.add_argument("--file", "-f", help="Path to notes file")
    plan_p.add_argument("--date", "-d", help="Date label (default: today)")
    plan_p.set_defaults(func=cmd_plan)

    run_p = sub.add_parser("run", help="Execute routing (briefings + optional API dispatch)")
    run_p.add_argument("--notes", "-n", help="Notes text")
    run_p.add_argument("--file", "-f", help="Path to notes file")
    run_p.add_argument("--date", "-d", help="Date label")
    run_p.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    run_p.add_argument("--asana", action="store_true", help="Create Asana tasks when executing")
    run_p.add_argument(
        "--granola",
        action="store_true",
        help="Include cached Granola meeting context in briefings (default: on when registry granola.enabled)",
    )
    run_p.add_argument(
        "--no-granola",
        action="store_true",
        help="Skip Granola context even when enabled in registry",
    )
    run_p.set_defaults(func=cmd_run)

    granola_p = sub.add_parser(
        "granola-queries",
        help="Print Granola MCP queries to run before dispatch (JSON)",
    )
    granola_p.add_argument("--notes", "-n", help="Optional notes to scope workstreams")
    granola_p.add_argument("--file", "-f", help="Optional notes file")
    granola_p.add_argument("--date", "-d", help="Date label")
    granola_p.set_defaults(func=cmd_granola_queries)

    save_g_p = sub.add_parser(
        "save-granola-context",
        help="Save Granola MCP results for a workstream (use _manager for Kenneth-wide context)",
    )
    save_g_p.add_argument("workstream", help="Workstream id or _manager")
    save_g_p.add_argument("file", help="Markdown file with meeting context")
    save_g_p.add_argument("--source", default="granola-mcp", help="Source label")
    save_g_p.set_defaults(func=cmd_save_granola_context)

    list_p = sub.add_parser("list-chats", help="List cloud agents from Cursor API")
    list_p.add_argument("--limit", type=int, default=30)
    list_p.set_defaults(func=cmd_list_chats)

    link_p = sub.add_parser("link-chat", help="Save agent id for a workstream")
    link_p.add_argument("workstream", help="Workstream id from registry.yaml")
    link_p.add_argument("agent_id", help="Cursor agent id (bc-* cloud or local id)")
    link_p.set_defaults(func=cmd_link_chat)

    poll_p = sub.add_parser(
        "poll-granola",
        help="Poll Granola API for new notes and run the dispatch pipeline",
    )
    poll_p.add_argument("--dry-run", action="store_true", help="Detect candidates without ingesting")
    poll_p.add_argument("--execute", action="store_true", help="Force live ingest (overrides registry dry_run)")
    poll_p.add_argument("--asana", action="store_true", help="Create Asana tasks")
    poll_p.add_argument("--granola", action="store_true", help="Include cached Granola context in briefings")
    poll_p.add_argument("--no-granola", action="store_true", help="Skip Granola context in briefings")
    poll_p.add_argument("--search", help="Ingest notes whose title matches this regex")
    poll_p.add_argument(
        "--include-processed",
        action="store_true",
        help="Re-process notes already in granola-state.json",
    )
    poll_p.add_argument(
        "--note-id",
        action="append",
        dest="note_id",
        metavar="ID",
        help="Force-ingest specific Granola note id(s), e.g. not_abc123",
    )
    poll_p.set_defaults(func=cmd_poll_granola)

    ingest_p = sub.add_parser(
        "ingest",
        help="Ingest notes from stdin/file, a Granola note id, or a webhook JSON payload",
    )
    ingest_p.add_argument("--notes", "-n", help="Notes text")
    ingest_p.add_argument("--file", "-f", help="Path to notes file")
    ingest_p.add_argument("--webhook", help="Path to Zapier/custom webhook JSON payload")
    ingest_p.add_argument("--note-id", help="Granola note id to fetch and ingest")
    ingest_p.add_argument("--search", help="Ingest notes whose title matches this regex")
    ingest_p.add_argument("--source", default="manual", help="Source label for logging")
    ingest_p.add_argument("--date", "-d", help="Date label")
    ingest_p.add_argument("--dry-run", action="store_true")
    ingest_p.add_argument("--execute", action="store_true", help="Force live ingest")
    ingest_p.add_argument("--asana", action="store_true")
    ingest_p.add_argument("--granola", action="store_true")
    ingest_p.add_argument("--no-granola", action="store_true")
    ingest_p.add_argument(
        "--no-cache-context",
        action="store_true",
        help="Do not write meeting context to data/granola-context/",
    )
    ingest_p.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
