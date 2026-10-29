"""Run the same questions through the real chat pipeline on two or more
models and write a side-by-side Markdown report (answer, tools used,
tokens, cost, time) for a human to judge.

Uses the production tool loop, search and prompts. Every run spends real
API money (roughly $0.01 per question on Haiku, $0.10 on Sonnet) and
writes chat_history + llm_usage rows tagged with session ids "eval_*".

  python scripts/compare_chat_models.py                          # default questions
  python scripts/compare_chat_models.py --models claude-sonnet-4-6,claude-haiku-5-5 \\
      --questions qs.txt --out /tmp/compare.md
"""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import routes.chat as chat  # noqa: E402

DEFAULT_QUESTIONS = [
    "What was the municipal tax rate in the most recent budget, and how has it changed over the last three years?",
    "How much does Atlantic Highlands spend on police, and what share of the budget is that?",
    "What did the council decide at its most recent meeting?",
    "What is the HHRSD total budget for the current school year and how much comes from local property taxes?",
    "List the largest contracts the borough awarded in the last two years.",
    "What has the planning board said about the harbor or waterfront recently?",
    "How much debt does the borough carry and when does it mature?",
    "What are the biggest year-over-year changes in the school district budget?",
    "Has the borough discussed shared services with Highlands? Summarize.",
    "What did the most recent audit flag, if anything?",
    "How much surplus (fund balance) does the borough have and how much is used in the budget?",
    "Find any discussion of the ferry or harbor fees in meeting minutes.",
]


class _Req:
    """Stand-in for the Starlette Request the stream polls for disconnects."""
    async def is_disconnected(self) -> bool:
        return False


async def run_one(model: str, effort: str, question: str) -> dict:
    chat.CHAT_MODEL = model
    chat.CHAT_EFFORT = effort
    req = chat.ChatRequest(query=question)
    system_blocks = chat._build_system_blocks(req, "")
    session_id = f"eval_{uuid.uuid4().hex[:12]}"
    answer, tools, done, error = [], [], {}, None
    t0 = time.monotonic()
    async for frame in chat._stream_claude(req, system_blocks, [], session_id, _Req(), None):
        if not frame.startswith("event:"):
            continue
        payload = json.loads(frame.split("data: ", 1)[1])
        kind = payload.get("type")
        if kind == "delta":
            answer.append(payload.get("content", ""))
        elif kind == "tool_call":
            tools.append(payload.get("description") or payload.get("name"))
        elif kind == "done":
            done = payload
        elif kind == "error":
            error = payload.get("content")
    return {
        "answer": "".join(answer).strip(),
        "tools": tools,
        "seconds": round(time.monotonic() - t0, 1),
        "input_tokens": done.get("input_tokens"),
        "output_tokens": done.get("output_tokens"),
        "cost": done.get("estimated_cost_usd"),
        "error": error,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="claude-sonnet-4-6,claude-haiku-5-5")
    ap.add_argument("--effort", default="", help="output_config.effort for every model, e.g. low")
    ap.add_argument("--questions", help="text file, one question per line")
    ap.add_argument("--out", default="compare_chat_models.md")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    questions = DEFAULT_QUESTIONS
    if args.questions:
        with open(args.questions) as f:
            questions = [q.strip() for q in f if q.strip()]

    totals = {m: {"cost": 0.0, "seconds": 0.0, "errors": 0} for m in models}
    lines = [f"# Chat model comparison\n\nModels: {', '.join(models)}"
             f"{'  ·  effort=' + args.effort if args.effort else ''}\n"]
    for i, q in enumerate(questions, 1):
        lines.append(f"\n## Q{i}. {q}\n")
        for m in models:
            print(f"[{i}/{len(questions)}] {m} …", flush=True)
            r = await run_one(m, args.effort, q)
            totals[m]["cost"] += r["cost"] or 0
            totals[m]["seconds"] += r["seconds"]
            totals[m]["errors"] += 1 if r["error"] else 0
            lines.append(
                f"### {m}\n\n_{r['seconds']}s · {len(r['tools'])} tool calls · "
                f"in {r['input_tokens']} / out {r['output_tokens']} tokens · ${r['cost']}_\n\n"
                f"Tools: {'; '.join(r['tools']) or 'none'}\n\n"
                + (f"**ERROR:** {r['error']}\n\n" if r["error"] else "")
                + f"{r['answer'] or '_(no answer)_'}\n"
            )

    summary = ["\n## Totals\n", "| Model | Total cost | Avg cost / question | Avg seconds | Errors |",
               "|---|---|---|---|---|"]
    n = len(questions)
    for m, t in totals.items():
        summary.append(f"| {m} | ${t['cost']:.3f} | ${t['cost'] / n:.4f} | {t['seconds'] / n:.1f} | {t['errors']} |")
    lines[1:1] = summary
    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    print("\n".join(summary))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
