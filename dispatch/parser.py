from __future__ import annotations

import re
from datetime import date

from dispatch.models import RoutingPlan, WorkItem, Workstream


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _score_line(line: str, workstream: Workstream) -> float:
    if not workstream.keywords:
        return 0.0
    haystack = _normalize(line)
    hits = sum(1 for kw in workstream.keywords if kw in haystack)
    if hits == 0:
        return 0.0
    return min(1.0, hits / max(1, len(workstream.keywords) * 0.35))


def _extract_lines(notes: str) -> list[str]:
    chunks: list[str] = []
    for raw in notes.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if not line:
            continue
        # Split compound lines: "Do X. Also Y" or "X; Y"
        parts = re.split(r"(?<=[.!?])\s+|;\s+|,\s+and also\s+|,\s+also\s+|\.\s+Also\s+", line)
        for part in parts:
            part = part.strip(" ,;.")
            if part:
                chunks.append(part)
    return chunks or [notes.strip()]


def parse_notes(
    notes: str,
    workstreams: list[Workstream],
    *,
    fallback_id: str = "general",
    min_match_score: float = 0.15,
    date_label: str | None = None,
) -> RoutingPlan:
    ws_by_id = {w.id: w for w in workstreams}
    plan = RoutingPlan(
        date_label=date_label or date.today().isoformat(),
        raw_notes=notes,
        workstreams=ws_by_id,
    )

    for idx, line in enumerate(_extract_lines(notes), start=1):
        best_id = fallback_id
        best_score = 0.0
        for ws in workstreams:
            if ws.id == fallback_id:
                continue
            score = _score_line(line, ws)
            if score > best_score:
                best_score = score
                best_id = ws.id

        if best_score < min_match_score:
            best_id = fallback_id

        item = WorkItem(text=line, workstream_id=best_id, score=best_score, source_line=idx)
        plan.items_by_workstream.setdefault(best_id, []).append(item)

    return plan


def format_briefing(
    plan: RoutingPlan,
    workstream_id: str,
    template: str,
    *,
    granola_context: str | None = None,
    manager_context: str | None = None,
    integration_context: str | None = None,
    note_source: str = "My notes + calls/1:1s (Granola)",
) -> str:
    items = plan.items_by_workstream.get(workstream_id, [])
    bullets = "\n".join(f"- {i.text}" for i in items) or "- (no items routed here)"

    context_parts: list[str] = []
    if manager_context:
        context_parts.append("### Calls & 1:1s\n\n" + manager_context.strip())
    if granola_context:
        context_parts.append("### Workstream meetings\n\n" + granola_context.strip())
    granola_block = "\n\n".join(context_parts) if context_parts else "_No call/1:1 context cached yet._"

    integration_block = integration_context.strip() if integration_context else "_No Pantry / data context cached yet._"

    return template.format(
        date=plan.date_label,
        items=bullets,
        granola_context=granola_block,
        integration_context=integration_block,
        note_source=note_source,
    )
