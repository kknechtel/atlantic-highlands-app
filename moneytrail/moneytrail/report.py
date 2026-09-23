"""Flag export: CSV for triage, Markdown for reading. Both carry file/line
citations so every lead goes back to its source document."""
import csv
import json

DISCLAIMER = (
    "Automated leads, not findings. Each item is a pattern in public records "
    "that warrants review; most have lawful explanations. Nothing here alleges "
    "wrongdoing by any person or entity. Verify against source documents before any use."
)


def fetch(con, min_score=0, rule=None):
    q = "SELECT rule, score, public_body, entity_id, entity_name, summary, evidence FROM flags WHERE score >= ?"
    args = [min_score]
    if rule:
        q += " AND rule = ?"
        args.append(rule)
    q += " ORDER BY score DESC, rule, entity_name"
    cols = ["rule", "score", "public_body", "entity_id", "entity_name", "summary", "evidence"]
    return [dict(zip(cols, r)) for r in con.execute(q, args).fetchall()]


def _citations(ev):
    out = []

    def walk(x):
        if isinstance(x, dict):
            if "file" in x and "line" in x:
                out.append((x["file"], x["line"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(ev)
    return [f"{f}:{ln}" for f, ln in sorted(set(out))]


def write_csv(flags, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "score", "public_body", "entity_name", "summary", "score_parts", "citations"])
        for fl in flags:
            ev = json.loads(fl["evidence"])
            w.writerow([fl["rule"], fl["score"], fl["public_body"] or "", fl["entity_name"] or "", fl["summary"],
                        " | ".join(f"{p} ({v:+d})" for p, v in ev.get("score_parts", [])),
                        " ".join(_citations(ev))])


def to_markdown(flags):
    lines = ["# moneytrail flags", "", f"> {DISCLAIMER}", "", f"{len(flags)} flag(s).", ""]
    for fl in flags:
        ev = json.loads(fl["evidence"])
        lines.append(f"## [{fl['score']:.0f}] {fl['rule']} — {fl['entity_name'] or 'n/a'}")
        lines.append("")
        lines.append(fl["summary"])
        lines.append("")
        for p, v in ev.get("score_parts", []):
            lines.append(f"- {v:+d}: {p}")
        if ev.get("caveat"):
            lines.append(f"- caveat: {ev['caveat']}")
        cites = _citations(ev)
        if cites:
            lines.append(f"- sources: {', '.join(cites)}")
        lines.append("")
    return "\n".join(lines)
