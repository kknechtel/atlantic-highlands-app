"""
Deck-aware AI chat. Streams Claude responses that can either:
  1. Answer free-form questions about the deck (no proposal), or
  2. Emit a `propose_section` tool call — a structured patch the editor
     applies to a section.

The frontend AskAIPanel renders proposal events as accept/reject cards.

Tools:
  - search_chunks: same RAG used by GlobalChat (so deck AI can ground claims)
  - propose_section: structured proposal — kind, title, body/headers/rows
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

import anthropic
from sqlalchemy.orm import Session

from config import ANTHROPIC_API_KEY
from database import SessionLocal
from services.rag_search import search_chunks

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert analyst helping the user build a presentation about Atlantic Highlands, NJ municipal affairs.

You can:
  1. Answer questions about the deck or the Atlantic Highlands document corpus.
  2. Propose section content via the `propose_section` tool.

Always call `search_chunks` first to ground your proposal in indexed documents.

## Section kinds

- `narrative`: Markdown prose. Include `[source: filename.pdf]` citations for every fact.
- `table`: Comparison table. Provide `headers` and `rows`.
- `react_component`: A React component for custom visualizations (charts, KPI tiles, layouts). Provide `tsx`.

## react_component scope

The TSX runs in a sandboxed `react-live` environment. You have these globals — DO NOT write `import` statements:

- React + hooks: `useState`, `useMemo`, `useCallback`, `useEffect`
- Recharts: `ResponsiveContainer`, `LineChart`, `BarChart`, `PieChart`, `AreaChart`, `Line`, `Bar`, `Pie`, `Area`, `XAxis`, `YAxis`, `CartesianGrid`, `Tooltip`, `Legend`, `Cell`, ...
- Lucide icons: `TrendingUp`, `TrendingDown`, `AlertTriangle`, `CheckCircle2`, `Calendar`, `DollarSign`, `Users`, `FileText`, `Globe`, ...
- AH primitives: `KPICard({label, value, delta?, trend?, sub?})`, `Callout({kind, title?, children})`, `Stat({label, value})`, `Section({title?, children})`
- `BRAND` constant: "#385854" (AH brand color, use for chart series)

NO `window`, `fetch`, `document`, `localStorage`. Any reference to those throws a clean ReferenceError.

Pattern:
```tsx
function MyChart() {
  const data = [
    { year: 'FY22', revenue: 12.5 },
    { year: 'FY23', revenue: 13.1 },
    { year: 'FY24', revenue: 14.2 },
  ];
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data}>
        <XAxis dataKey="year" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="revenue" fill={BRAND} />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

Use `react_component` whenever a visualization would land harder than a markdown chart block — e.g. multi-pane KPI dashboards, comparative bar+line overlays, custom layouts.
"""


def _tool_defs() -> list[dict]:
    return [
        {
            "name": "search_chunks",
            "description": "Search passages across the indexed Atlantic Highlands document corpus.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
        {
            "name": "propose_section",
            "description": "Propose a new or rewritten section for the deck. The user accepts or rejects from the editor.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "string", "description": "Existing section ID to rewrite, or omit to propose a new section."},
                    "kind": {"type": "string", "enum": ["narrative", "table", "react_component"]},
                    "title": {"type": "string"},
                    "body": {"type": "string", "description": "Markdown body for narrative sections. Use [source: filename.pdf] citations."},
                    "headers": {"type": "array", "items": {"type": "string"}, "description": "Column headers for table sections."},
                    "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Row data for table sections."},
                    "caption": {"type": "string"},
                    "tsx": {"type": "string", "description": "TSX source for react_component sections. NO imports — see system prompt for the curated scope."},
                    "data": {"description": "Optional structured data exposed to TSX as `data` identifier."},
                    "rationale": {"type": "string", "description": "1-2 sentences explaining why this section. Shown to the user."},
                },
                "required": ["kind", "title"],
            },
        },
    ]


def _exec_search_chunks(db: Session, args: dict) -> dict:
    rows = search_chunks(db, query=args["query"], top_k=int(args.get("top_k", 8)))
    return {
        "count": len(rows),
        "chunks": [
            {
                "filename": r["filename"],
                "fiscal_year": r.get("fiscal_year"),
                "doc_type": r.get("doc_type"),
                "content": (r.get("content") or "")[:1800],
                "score": float(r.get("score") or 0),
            }
            for r in rows
        ],
    }


def _sse(event: str, data: dict) -> str:
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


async def stream_deck_chat(
    user_message: str,
    sections_summary: str,
    history: Optional[list[dict]] = None,
) -> AsyncGenerator[str, None]:
    if not ANTHROPIC_API_KEY:
        yield _sse("error", {"content": "ANTHROPIC_API_KEY not configured"})
        return

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    tools = _tool_defs()

    system = SYSTEM_PROMPT + "\n\n## CURRENT DECK\n\n" + sections_summary

    messages: list[dict] = list(history or [])[-20:]
    messages.append({"role": "user", "content": user_message})

    try:
        for _ in range(6):
            async with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=12000,
                system=system,
                tools=tools,
                messages=messages,
            ) as stream:
                async for event in stream:
                    et = getattr(event, "type", None)
                    if et == "content_block_start":
                        block = event.content_block
                        if getattr(block, "type", None) == "tool_use":
                            yield _sse("tool_use", {"name": block.name})
                    elif et == "content_block_delta":
                        delta = event.delta
                        if getattr(delta, "type", None) == "text_delta":
                            yield _sse("delta", {"content": delta.text})

                final = await stream.get_final_message()
                tool_blocks = [b for b in final.content if getattr(b, "type", None) == "tool_use"]
                if not tool_blocks or final.stop_reason != "tool_use":
                    yield _sse("done", {})
                    return

                results = []
                for tb in tool_blocks:
                    if tb.name == "propose_section":
                        # Surface the proposal to the UI as its own event so the
                        # editor can render an accept/reject card; don't let the
                        # full proposal text echo back into Claude's context.
                        yield _sse("proposal", {"input": tb.input})
                        results.append({
                            "type": "tool_result", "tool_use_id": tb.id,
                            "content": json.dumps({"ok": True, "ack": "Proposal sent to editor."}),
                        })
                        continue
                    if tb.name == "search_chunks":
                        sess = SessionLocal()
                        try:
                            res = await asyncio.to_thread(_exec_search_chunks, sess, tb.input)
                        finally:
                            sess.close()
                        yield _sse("tool_result", {
                            "name": tb.name,
                            "summary": f"Found {res['count']} passages",
                        })
                        results.append({
                            "type": "tool_result", "tool_use_id": tb.id,
                            "content": json.dumps(res)[:30000],
                        })
                        continue
                    results.append({
                        "type": "tool_result", "tool_use_id": tb.id,
                        "content": json.dumps({"error": f"unknown_tool:{tb.name}"}),
                    })

                messages.append({"role": "assistant", "content": final.content})
                messages.append({"role": "user", "content": results})

        yield _sse("done", {"reason": "iteration_limit"})

    except anthropic.APIStatusError as exc:
        log.error("Deck chat API error: %s", exc)
        yield _sse("error", {"content": str(exc)[:300]})
    except Exception as exc:
        log.exception("Deck chat failed")
        yield _sse("error", {"content": str(exc)[:300]})


def build_sections_summary(sections: list) -> str:
    """Compact summary of the current deck so Claude knows what's there."""
    if not sections:
        return "(empty deck — no sections yet)"
    lines = []
    for i, s in enumerate(sections):
        sid = s.get("id", f"sec_{i}")
        kind = s.get("kind", "?")
        title = s.get("title", "(untitled)")
        body_preview = ""
        if kind == "narrative":
            body_preview = (s.get("body") or "")[:200]
        elif kind == "table":
            body_preview = f"{len(s.get('headers', []))} cols × {len(s.get('rows', []))} rows"
        elif kind == "attachment":
            body_preview = f"attachment {s.get('attachment_id', '?')}"
        lines.append(f"- [{sid}] {kind}: **{title}** — {body_preview}")
    return "\n".join(lines)
