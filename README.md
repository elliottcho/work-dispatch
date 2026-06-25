# Work Dispatch

Route **Kenneth's day/week priorities** into the right Cursor chats and Asana tasks — without manually copying notes into every project.

## How it works

```
You paste Kenneth's notes
        ↓
   Dispatch chat (skill) parses & confirms routing
        ↓
   CLI orchestrator
        ├── Writes briefings → each project's docs/kenneth-dispatch-YYYY-MM-DD.md
        ├── Sends follow-ups → linked cloud agents (Cursor API)
        └── Creates tasks → Asana (optional)
```

## Quick start

```bash
cd ~/Projects/work-dispatch
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # add CURSOR_API_KEY, optional ASANA_* 
```

### 1. Paste notes (dry run)

```bash
dispatch plan --notes "Ship Lisle sourcing batch. Follow up with Aris on activation app."
```

### 2. Execute routing

```bash
dispatch run --notes "..." --dry-run   # preview
dispatch run --notes "..."             # write briefings + dispatch to linked chats
dispatch run --notes "..." --asana     # also create Asana tasks
```

### 3. Link existing Cursor chats

After you have stable chats per workstream:

```bash
dispatch list-chats                    # cloud agents (bc-* ids)
dispatch link-chat hk-vetting bc-abc123
dispatch link-chat pro-activation bc-def456
```

Edit `dispatch/registry.yaml` to add keywords, Asana project names, and local project paths.

## Conversational interface

Use a dedicated Cursor chat titled **"Kenneth Dispatch"** — the personal skill `work-dispatch` teaches the agent to:

1. Accept raw notes from Kenneth
2. Show a routing table (workstream → items → target chat)
3. Ask for confirmation
4. Run `dispatch run` from `~/Projects/work-dispatch`

## Configuration

| File | Purpose |
|------|---------|
| `dispatch/registry.yaml` | Workstreams, keywords, chat titles, agent IDs, Asana projects |
| `.env` | `CURSOR_API_KEY`, `ASANA_ACCESS_TOKEN`, `ASANA_WORKSPACE_GID` |

### Workstreams (default)

- **hk-vetting** → `~/Projects/hk-vetting-funnel`
- **pro-activation** → `~/Projects/pro-activation`
- **general** → fallback inbox

## Notes

- **Cloud agents** (`bc-*`): full API dispatch via Cursor Cloud Agents API
- **Local IDE chats**: write briefings to disk; link agent IDs when `cursor-sdk` is available, or paste briefings manually
- **Asana**: set `project_name` per workstream in registry + `ASANA_WORKSPACE_GID` in `.env`
