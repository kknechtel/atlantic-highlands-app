"""Entity resolution: turn every name that appears in any source into a
mention, match mentions pairwise inside blocks, and cluster with union-find.

Every accepted pair is written to er_edges with its score and the rule that
accepted it, so a cluster can be explained (or challenged) edge by edge.
Nothing here is probabilistic-magic; thresholds live in config.py.

Known gaps (by design, for now):
- Blocking is first-token and zip5. A typo in the first token of a name with
  no zip on either side will be missed.
- No business-registry data yet, so officers/agents don't link entities.
"""
from collections import Counter, defaultdict

import numpy as np
from rapidfuzz import fuzz, process

from moneytrail import config as C
from moneytrail import normalize as N
from moneytrail.schema import bulk_insert

# (table, id col, name col, role, kind or None=use row's contributor_kind, has address)
MENTION_SOURCES = [
    ("contributions", "contributor_name", "contributor", None, True),
    ("contributions", "employer", "employer", "org", False),
    ("be_disclosures", "business_name", "business", "org", True),
    ("awards", "vendor_name", "vendor", "org", True),
    ("payments", "vendor_name", "vendor", "org", True),
    ("employees", "name", "employee", "person", True),
]

# Employer strings that carry no entity information.
EMPLOYER_NOISE = {"", "SELF", "SELF EMPLOYED", "RETIRED", "NONE", "N A", "NA", "HOMEMAKER",
                  "NOT EMPLOYED", "UNEMPLOYED", "INFORMATION REQUESTED", "STUDENT"}


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def build_mentions(con):
    con.execute("DELETE FROM mentions")
    rows, mid = [], 0
    for table, col, role, kind, has_addr in MENTION_SOURCES:
        kind_expr = "contributor_kind" if kind is None else f"'{kind}'"
        addr_expr = "street, zip" if has_addr else "NULL, NULL"
        for src_id, name, k, street, z in con.execute(
            f"SELECT id, {col}, {kind_expr}, {addr_expr} FROM {table} WHERE {col} IS NOT NULL"
        ).fetchall():
            norm = N.norm_person(name) if k == "person" else N.norm_org(name)
            if not norm or (role == "employer" and norm in EMPLOYER_NOISE):
                continue
            mid += 1
            rows.append((mid, table, src_id, role, k, name, norm, N.norm_addr(street), N.zip5(z)))
    if rows:
        bulk_insert(con, "mentions", ["mention_id", "src_table", "src_id", "role", "kind", "raw_name", "norm_name", "norm_addr", "zip5"], rows)
    return len(rows)


def _match(a, b):
    """a, b: (norm_name, norm_addr, zip5). Returns (score, method) or None."""
    if a[0] == b[0]:
        return 100.0, "exact_name"
    score = fuzz.token_sort_ratio(a[0], b[0])
    same_addr = bool(a[1]) and a[1] == b[1] and not N.is_po_box(a[1])
    same_zip = bool(a[2]) and a[2] == b[2]
    if score >= C.ER_NAME_ALONE:
        return score, "name"
    if score >= C.ER_NAME_WITH_ZIP and (same_zip or same_addr):
        return score, "name+zip" if not same_addr else "name+addr"
    if score >= C.ER_NAME_WITH_ADDR and same_addr:
        return score, "name+addr"
    return None


def resolve(con):
    n = build_mentions(con)
    con.execute("DELETE FROM er_edges; DELETE FROM mention_entity; DELETE FROM entities;")
    ms = con.execute("SELECT mention_id, kind, raw_name, norm_name, norm_addr, zip5 FROM mentions").fetchall()

    # Collapse identical (kind, name, addr, zip) keys first — most rows are repeats.
    keys = defaultdict(list)
    for mid, kind, raw, nn, na, z in ms:
        keys[(kind, nn, na, z)].append(mid)

    uf, edges = _UF(), []
    for mids in keys.values():
        for m in mids[1:]:
            uf.union(mids[0], m)

    blocks = defaultdict(set)
    for key in keys:
        kind, nn, na, z = key
        blocks[(kind, "t", nn.split()[0])].add(key)
        if z:
            blocks[(kind, "z", z)].add(key)

    seen = set()
    for members in blocks.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        names = [k[1] for k in members]
        # C-speed scoring; pairs under the lowest acceptance bar come back as 0.
        mat = process.cdist(names, names, scorer=fuzz.token_sort_ratio,
                            score_cutoff=C.ER_NAME_WITH_ADDR, workers=-1)
        for i, j in zip(*np.nonzero(np.triu(mat, k=1))):
            a, b = members[i], members[j]
            if (a, b) in seen:
                continue
            seen.add((a, b))
            m = _match(a[1:], b[1:])
            if m:
                ra, rb = keys[a][0], keys[b][0]
                uf.union(ra, rb)
                edges.append((ra, rb, m[0], m[1]))

    if edges:
        bulk_insert(con, "er_edges", ["a", "b", "score", "method"], edges)

    by_mid = {m[0]: m for m in ms}
    clusters = defaultdict(list)
    for mid in by_mid:
        clusters[uf.find(mid)].append(mid)
    me_rows, ent_rows = [], []
    for eid, mids in clusters.items():
        names = Counter(by_mid[m][2].strip() for m in mids)
        ent_rows.append((eid, by_mid[eid][1], names.most_common(1)[0][0], len(mids)))
        me_rows.extend((m, eid) for m in mids)
    if me_rows:
        bulk_insert(con, "mention_entity", ["mention_id", "entity_id"], me_rows)
        bulk_insert(con, "entities", ["entity_id", "kind", "canonical_name", "n_mentions"], ent_rows)
    return {"mentions": n, "entities": len(ent_rows), "fuzzy_edges": len(edges)}
