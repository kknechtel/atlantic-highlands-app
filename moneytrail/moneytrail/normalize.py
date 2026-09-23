"""Name, address, amount and date normalization for matching."""
import re
from datetime import date, datetime

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")

ORG_SUFFIXES = {
    "LLC", "L L C", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
    "LTD", "LIMITED", "LP", "LLP", "PC", "PA", "PLLC", "PLC", "THE", "OF", "NJ",
}
ORG_ABBREV = {
    "ASSOC": "ASSOCIATES", "ASSOCS": "ASSOCIATES", "ASSN": "ASSOCIATION",
    "ENGRS": "ENGINEERS", "ENGR": "ENGINEERING", "ENG": "ENGINEERING",
    "CONST": "CONSTRUCTION", "CONSTR": "CONSTRUCTION", "CONTR": "CONTRACTING",
    "SVCS": "SERVICES", "SVC": "SERVICE", "SERV": "SERVICES", "MGMT": "MANAGEMENT",
    "BROS": "BROTHERS", "INTL": "INTERNATIONAL", "NATL": "NATIONAL",
    "TWP": "TOWNSHIP", "BORO": "BOROUGH", "CNTY": "COUNTY",
}
PERSON_SUFFIXES = {"JR", "SR", "II", "III", "IV", "ESQ", "MR", "MRS", "MS", "DR"}

ADDR_ABBREV = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "BOULEVARD": "BLVD", "LANE": "LN", "COURT": "CT", "PLACE": "PL", "HIGHWAY": "HWY",
    "ROUTE": "RT", "RTE": "RT", "PARKWAY": "PKWY", "TERRACE": "TER", "CIRCLE": "CIR",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "SQUARE": "SQ",
    "TURNPIKE": "TPKE", "PIKE": "PIKE", "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD",
}
_UNIT = re.compile(r"\b(SUITE|STE|UNIT|APT|FL|FLOOR|RM|ROOM|BLDG|#)\s*\w*\b.*$")
_POBOX = re.compile(r"\bP\s*O\s*BOX\b|\bPOST OFFICE BOX\b|\bPOB\b")


def _clean(s):
    s = (s or "").upper().replace("&", " AND ")
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def norm_org(name):
    toks = [ORG_ABBREV.get(t, t) for t in _clean(name).split()]
    # Collapse "L L C" style dotted suffixes before stripping.
    joined = " ".join(toks).replace("L L C", "LLC").replace("L L P", "LLP").replace("P C", "PC")
    toks = [t for t in joined.split() if t not in ORG_SUFFIXES]
    return " ".join(toks)


def norm_person(name):
    """'SMITH, JOHN A.' and 'John A Smith Jr' -> 'JOHN SMITH' (order-insensitive
    matching is left to token_sort_ratio; initials and suffixes dropped)."""
    raw = (name or "").upper()
    if "," in raw:
        last, _, first = raw.partition(",")
        raw = f"{first} {last}"
    toks = [t for t in _clean(raw).split() if len(t) > 1 and t not in PERSON_SUFFIXES]
    return " ".join(toks)


def norm_addr(street):
    s = _clean(street)
    if not s:
        return ""
    if _POBOX.search(s):
        m = re.search(r"BOX\s*(\w+)", s)
        return f"PO BOX {m.group(1)}" if m else "PO BOX"
    s = _UNIT.sub("", s).strip()
    return " ".join(ADDR_ABBREV.get(t, t) for t in s.split())


def is_po_box(norm_address):
    return norm_address.startswith("PO BOX")


def zip5(z):
    d = re.sub(r"\D", "", str(z or ""))
    return d[:5] if len(d) >= 5 else ""


def parse_amount(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return None
    amt = float(s)
    return -amt if neg else amt


_DATE_FMTS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y", "%d-%b-%Y", "%b %d, %Y", "%B %d, %Y")


def parse_date(v):
    if v is None or isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    s = s.split(" ")[0] if re.match(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4} ", s) else s
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date: {v!r}")


def looks_like_org(name):
    """Heuristic for ELEC rows that don't say whether the contributor is an
    individual. Wrong guesses only affect which normalizer is used."""
    u = f" {_clean(name)} "
    markers = (" LLC ", " INC ", " CORP ", " CO ", " COMPANY ", " PAC ", " COMMITTEE ", " ASSOCIATES ",
               " LLP ", " PC ", " PA ", " GROUP ", " UNION ", " LOCAL ", " ASSOCIATION ", " FUND ",
               " PARTNERS ", " ENGINEERING ", " CONSTRUCTION ", " SERVICES ", " LAW ", " FIRM ")
    return any(m in u for m in markers)
