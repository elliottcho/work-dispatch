from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from dispatch.executor import execute_plan, plan_to_json
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
    run_p.set_defaults(func=cmd_run)

    list_p = sub.add_parser("list-chats", help="List cloud agents from Cursor API")
    list_p.add_argument("--limit", type=int, default=30)
    list_p.set_defaults(func=cmd_list_chats)

    link_p = sub.add_parser("link-chat", help="Save agent id for a workstream")
    link_p.add_argument("workstream", help="Workstream id from registry.yaml")
    link_p.add_argument("agent_id", help="Cursor agent id (bc-* cloud or local id)")
    link_p.set_defaults(func=cmd_link_chat)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
