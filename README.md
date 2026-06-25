# Work Dispatch

Route **Kenneth's day/week priorities** into the right Cursor chats and Asana tasks — without manually copying notes into every project.

## How it works

```
Granola note (new meeting / conversation)
        ↓
   poll-granola OR ingest (API / webhook / manual)
        ↓
   Parse action items → allocate workstreams
        ↓
   CLI orchestrator
        ├── Cache meeting context → data/granola-context/
        ├── Writes briefings → docs/kenneth-dispatch-YYYY-MM-DD.md
        ├── Sends follow-ups → linked cloud agents (Cursor API)
        └── Creates tasks → Asana (optional)
```

**Manual path** (paste Kenneth's notes):

```
You paste Kenneth's notes
        ↓
   Granola MCP — recent meetings, decisions, action items
        ↓
   Dispatch chat (skill) parses, reconciles, confirms routing
        ↓
   dispatch run
```

See [docs/automation-flow.md](docs/automation-flow.md) for the full automation flowchart and cron setup.

## Connect Granola

The **Granola plugin** (skills, commands) and the **Granola MCP server** (meeting queries) are separate. Enabling the plugin alone does not connect MCP — this project ships the MCP config in `.cursor/mcp.json`.

### One-time setup

1. **Open this folder in Cursor** — `~/Projects/work-dispatch` must be the workspace root (not your home directory).
2. **Confirm MCP config exists** — `.cursor/mcp.json` should contain:
   ```json
   {
     "mcpServers": {
       "granola": {
         "url": "https://mcp.granola.ai/mcp"
       }
     }
   }
   ```
3. **Reload MCP** — `Cmd+Shift+P` → **Developer: Reload Window** (or restart Cursor).
4. **Authenticate** — Open **Settings → Tools & MCP**. Find **granola** and click **Connect** / complete OAuth in the browser. Sign in with the same email as your Granola app (check Granola → Settings).
5. **Verify** — In a Kenneth Dispatch chat, ask: *"Which Granola account am I signed in with?"* It should call `get_account_info` and return your email + workspace.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| Granola plugin enabled but no MCP tools in chat | MCP server not configured — ensure `.cursor/mcp.json` exists and reload Cursor |
| "Needs authentication" in MCP settings | Click Connect next to granola and complete browser OAuth |
| Wrong meetings / empty results | Ask *"Which Granola account am I signed in with?"* — reconnect with your work Granola email |
| Enterprise workspace | Admin must enable MCP in Granola **Settings → Workspace → General** |
| Free plan | Only notes from the last 30 days are queryable |

Plugin skills/commands work globally; **MCP tools only appear when this project (or your global `~/.cursor/mcp.json`) includes the granola server.**

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

### 2. Pull Granola context (in Dispatch chat or manually)

The dispatch skill uses **Granola MCP** (`query_granola_meetings`, `list_meetings`, `get_meetings`) to enrich briefings with meeting decisions.

```bash
dispatch granola-queries --notes "Your Kenneth notes here"
# Run each query via Granola MCP in Cursor, save results:
dispatch save-granola-context _manager /tmp/kenneth.md
dispatch save-granola-context hk-vetting /tmp/hk.md
```

Cached context lives in `data/granola-context/` and is merged into briefings when `--granola` is set (on by default via `registry.yaml`).

### 3. Automated Granola ingest

Granola has **no webhooks** — use polling or a Cursor Automation cron.

```bash
# Detect new notes (no ingest)
dispatch poll-granola

# Ingest from API (dry-run by default in registry.yaml)
dispatch ingest --search "day 4" --dry-run

# Push briefings to linked chats
dispatch ingest --file examples/day4-granola-note.md --execute

# Cron / Cursor Automation (every 15 min)
dispatch ingest --execute
```

Requires `GRANOLA_API_KEY` for API polling. State tracked in `data/granola-state.json`. See `docs/automation-flow.md`.

### 4. Execute routing (manual notes)

```bash
dispatch run --notes "..." --dry-run   # preview
dispatch run --notes "..." --granola   # include cached Granola context
dispatch run --notes "..." --granola --asana
```

### 5. Link existing Cursor chats

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
| `.cursor/mcp.json` | Granola MCP server URL for this workspace |
| `.cursor/settings.json` | Enables Granola plugin (skills/commands) in this project |
| `dispatch/registry.yaml` | Workstreams, keywords, Granola queries, chat titles, agent IDs, Asana projects, **automation** |
| `data/granola-context/` | Cached meeting context from Granola (per workstream + `_manager`) |
| `data/granola-state.json` | Poll watermark + processed note ids for automation |
| `docs/automation-flow.md` | Full automation flowchart, cron, Zapier, Cursor Automation setup |
| `.cursor/rules/granola-dispatch.mdc` | Reminds agents to read Granola before dispatching |
| `.env` | `CURSOR_API_KEY`, `GRANOLA_API_KEY`, `ASANA_ACCESS_TOKEN`, `ASANA_WORKSPACE_GID` |

### Workstreams (default)

- **hk-vetting** → `~/Projects/hk-vetting-funnel`
- **pro-activation** → `~/Projects/pro-activation`
- **general** → fallback inbox

## Notes

- **Granola MCP**: OAuth in Cursor chats for ad-hoc queries; CLI automation uses **REST API** (`GRANOLA_API_KEY`) for polling
- **Granola webhooks**: not available natively; use `poll-granola`, cron, or Zapier → `ingest --webhook`
- **Cloud agents** (`bc-*`): full API dispatch via Cursor Cloud Agents API
- **Local IDE chats**: write briefings to disk; link agent IDs when `cursor-sdk` is available, or paste briefings manually
- **Asana**: set `project_name` per workstream in registry + `ASANA_WORKSPACE_GID` in `.env`
