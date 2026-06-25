from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "data" / "runs"


def build_flowchart_mermaid(meta: dict[str, Any], *, command: str = "run") -> str:
    integrations = meta.get("integrations", {})
    stages = integrations.get("stages") or _default_stages()
    manager = meta.get("manager", "Kenneth")

    lines = ["flowchart TD"]
    lines.append('    START(["Dispatch triggered<br/>' + command.replace("_", " ") + '"])')

    prev = "START"
    for stage in sorted(stages, key=lambda s: s.get("order", 99)):
        sid = stage["id"]
        label = stage.get("label", sid.replace("_", " ").title())
        node_id = sid.upper().replace("-", "_")
        if stage.get("optional"):
            label += "<br/>(optional)"
        lines.append(f'    {node_id}["{label}"]')
        lines.append(f"    {prev} --> {node_id}")
        prev = node_id

    lines.append(f'    {prev} --> DONE(["Briefings + chats live"])')
    lines.append("")
    lines.append('    classDef mcp fill:#e8f4fc,stroke:#2563eb')
    lines.append('    classDef internal fill:#f0fdf4,stroke:#16a34a')
    lines.append('    classDef gate fill:#fef9c3,stroke:#ca8a04')

    mcp_ids = {
        s["id"].upper().replace("-", "_")
        for s in stages
        if s.get("mcp_server") or s.get("type") == "mcp"
    }
    gate_ids = {"FLOWCHART", "ROUTE"}
    internal_ids = {"PUSH", "ROUTE"}

    if mcp_ids:
        lines.append(f"    class {','.join(sorted(mcp_ids))} mcp")
    if gate_ids & {s["id"].upper().replace("-", "_") for s in stages}:
        lines.append("    class FLOWCHART gate")
    if internal_ids:
        lines.append(f"    class {','.join(sorted(internal_ids & {s['id'].upper().replace('-', '_') for s in stages}))} internal")

    return "\n".join(lines)


def build_flowchart_explanation(meta: dict[str, Any], *, command: str = "run") -> str:
    manager = meta.get("manager", "Kenneth")
    integrations = meta.get("integrations", {})
    confluence = integrations.get("confluence", {})
    space = confluence.get("space_key", "PANTRY")

    return f"""## What happens on each dispatch run

This run (`{command}`) follows a fixed pipeline. **Nothing is pushed to a project or Cursor chat until enrichment stages complete** and you confirm routing.

| Stage | Source | Purpose |
|-------|--------|---------|
| **0 — Flowchart** | This document | You see the pipeline before work starts |
| **1 — Granola** | Meeting MCP | Calls & 1:1s — decisions and action items (Kenneth sets direction; you capture it) |
| **2 — Confluence (Pantry)** | Atlassian MCP | Internal docs in space `{space}` — specs, runbooks, context |
| **3 — Redshift (Finch)** | finch-redshift MCP | Live funnel / activation metrics from warehouse |
| **4 — Mode** | mode-analytics MCP | Curated reports and SQL definitions |
| **5 — Route** | dispatch CLI | Keyword-match items → workstreams (HK vetting, Pro activation, …) |
| **6 — Replit** | Replit MCP | Optional sandboxes / prototypes when an item needs a spike |
| **7 — Push** | Cursor API + files | Briefings → `docs/kenneth-dispatch-*.md` + linked chats |

**Input types:** (1) **your notes** from what {manager} told you, (2) **team calls** in Granola, (3) **1:1s** in Granola. Reconcile all three before pushing to project chats.
"""


def emit_flowchart(
    meta: dict[str, Any],
    *,
    command: str = "run",
    plan_summary: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mermaid = build_flowchart_mermaid(meta, command=command)
    explanation = build_flowchart_explanation(meta, command=command)

    workstream_section = ""
    if plan_summary:
        rows = "\n".join(
            f"- **{r.get('workstream', '?')}** → {', '.join(r.get('items', [])) or '(none)'}"
            for r in plan_summary
        )
        workstream_section = f"\n## Planned routing (this run)\n\n{rows}\n"

    markdown = f"""# Dispatch workflow — {meta.get('manager', 'Kenneth')} priorities

Generated: {datetime.now(timezone.utc).isoformat()}
Command: `{command}`

## Flowchart

```mermaid
{mermaid}
```

{explanation}
{workstream_section}
"""

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RUNS_DIR / f"{stamp}-{command}-flowchart.md"
    path.write_text(markdown)

    return {
        "flowchart_path": str(path),
        "mermaid": mermaid,
        "explanation": explanation.strip(),
        "markdown": markdown,
    }


def _default_stages() -> list[dict[str, Any]]:
    return [
        {"id": "flowchart", "order": 0, "label": "Show flowchart", "type": "gate"},
        {"id": "granola", "order": 1, "label": "Granola meetings", "mcp_server": "granola", "type": "mcp"},
        {"id": "confluence", "order": 2, "label": "Confluence Pantry", "mcp_server": "atlassian", "type": "mcp"},
        {"id": "redshift", "order": 3, "label": "Redshift via Finch", "mcp_server": "finch-redshift", "type": "mcp"},
        {"id": "mode", "order": 4, "label": "Mode reports", "mcp_server": "mode-analytics", "type": "mcp"},
        {"id": "route", "order": 5, "label": "Parse & route", "type": "internal"},
        {"id": "replit", "order": 6, "label": "Replit sandbox", "mcp_server": "replit", "type": "mcp", "optional": True},
        {"id": "push", "order": 7, "label": "Push briefings & chats", "type": "internal"},
    ]
