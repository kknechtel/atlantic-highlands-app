"""python -m moneytrail <command>

  init                         create the DuckDB schema
  load <type> <csv> [--note]   load a CSV (types: contributions, be_disclosures,
                               awards, payments, employees, recipient_map,
                               public_bodies, disclosures)
  resolve                      run entity resolution
  flag [--only rule ...]       run red-flag rules
  report [--csv F] [--md F] [--min-score N] [--rule R]
  entity <name>                show a resolved entity, its mentions and match edges
  stats                        row counts
  fetch [--source S ...] [--refresh] [--limit N]
                               download linked documents from sources.py
  text                         extract PDF text for fetched documents
  docs [--class C]             inventory of fetched documents
"""
import argparse
import sys

import duckdb

from moneytrail import loaders, report, resolve, rules, schema

DEFAULT_DB = "data/moneytrail.duckdb"
DEFAULT_RAW = "data/raw"


def connect(path):
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = duckdb.connect(path)
    schema.init(con)
    return con


def main(argv=None):
    ap = argparse.ArgumentParser(prog="moneytrail", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("load")
    p.add_argument("source_type", choices=sorted(loaders.SPECS))
    p.add_argument("paths", nargs="+")
    p.add_argument("--note")
    sub.add_parser("resolve")
    p = sub.add_parser("flag")
    p.add_argument("--only", nargs="*")
    p = sub.add_parser("report")
    p.add_argument("--csv")
    p.add_argument("--md")
    p.add_argument("--min-score", type=float, default=0)
    p.add_argument("--rule")
    p = sub.add_parser("entity")
    p.add_argument("name")
    sub.add_parser("stats")
    p = sub.add_parser("fetch")
    p.add_argument("--source", nargs="*")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--limit", type=int)
    sub.add_parser("text")
    p = sub.add_parser("docs")
    p.add_argument("--class", dest="doc_class")
    ap.add_argument("--raw", default=DEFAULT_RAW)
    a = ap.parse_args(argv)

    con = connect(a.db)
    if a.cmd == "init":
        print(f"schema ready at {a.db}")
    elif a.cmd == "load":
        for path in a.paths:
            fid, n = loaders.load_csv(con, a.source_type, path, note=a.note)
            print(f"{path}: " + (f"already loaded (file_id {fid})" if n is None else f"{n} rows (file_id {fid})"))
        print("re-run `resolve` and `flag` to refresh results")
    elif a.cmd == "resolve":
        print(resolve.resolve(con))
    elif a.cmd == "flag":
        for k, v in rules.run_all(con, a.only).items():
            print(f"{k:28s} {v}")
    elif a.cmd == "report":
        flags = report.fetch(con, a.min_score, a.rule)
        if a.csv:
            report.write_csv(flags, a.csv)
            print(f"wrote {len(flags)} flags to {a.csv}")
        md = report.to_markdown(flags)
        if a.md:
            with open(a.md, "w") as f:
                f.write(md)
            print(f"wrote {a.md}")
        if not a.csv and not a.md:
            print(md)
    elif a.cmd == "entity":
        from moneytrail.normalize import norm_org, norm_person
        ents = con.execute(
            "SELECT DISTINCT e.* FROM entities e JOIN mention_entity me USING (entity_id) JOIN mentions m USING (mention_id) "
            "WHERE m.norm_name IN (?, ?) OR e.canonical_name ILIKE ?",
            [norm_org(a.name), norm_person(a.name), f"%{a.name}%"]).fetchall()
        for eid, kind, cname, n in ents:
            print(f"\n[{eid}] {cname} ({kind}, {n} mentions)")
            for r in con.execute("SELECT src_table, role, raw_name, norm_addr, zip5, count(*) FROM mentions "
                                 "JOIN mention_entity USING (mention_id) WHERE entity_id=? GROUP BY ALL ORDER BY 6 DESC", [eid]).fetchall():
                print(f"   {r[0]:15s} {r[1]:12s} {r[2]!r:45s} {r[3] or '':30s} {r[4] or '':5s} x{r[5]}")
            for r in con.execute("SELECT ma.raw_name, mb.raw_name, x.score, x.method FROM er_edges x "
                                 "JOIN mentions ma ON ma.mention_id=x.a JOIN mentions mb ON mb.mention_id=x.b "
                                 "JOIN mention_entity me ON me.mention_id=x.a WHERE me.entity_id=?", [eid]).fetchall():
                print(f"   edge: {r[0]!r} ~ {r[1]!r}  {r[2]:.0f} via {r[3]}")
        if not ents:
            print("no match")
    elif a.cmd == "fetch":
        from moneytrail import fetch
        print(fetch.fetch_all(con, a.raw, only=a.source, refresh=a.refresh, limit=a.limit))
    elif a.cmd == "text":
        from moneytrail import fetch
        r = fetch.extract_text(con, a.raw)
        print(f"extracted {r['extracted']}; {len(r['needs_ocr'])} look scanned (need OCR)")
        for x in r["needs_ocr"]:
            print("  ", x)
    elif a.cmd == "docs":
        from moneytrail import fetch
        fetch.init(con)
        q = "SELECT source, doc_class, count(*), min(doc_date), max(doc_date) FROM documents"
        args = []
        if a.doc_class:
            q = ("SELECT doc_date, title, url FROM documents WHERE doc_class = ? ORDER BY doc_date NULLS LAST")
            args = [a.doc_class]
        else:
            q += " GROUP BY ALL ORDER BY 1, 2"
        for r in con.execute(q, args).fetchall():
            print("  ".join(str(x) for x in r))
    elif a.cmd == "stats":
        for t in ("source_files", "public_bodies", "contributions", "be_disclosures", "awards", "payments",
                  "employees", "disclosures",
                  "recipient_map", "mentions", "entities", "flags"):
            print(f"{t:16s} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
