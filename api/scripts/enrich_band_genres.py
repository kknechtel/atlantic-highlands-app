"""Infer genre (and any *sourced* rating) for the acts we list, from the
bands' own pages.

We list ~120 distinct acts a season and know almost nothing about most of
them. The ported Edgewater guide only covers 40 party/cover bands and
matches about 5 of ours, so band pages are nearly bare.

Method — every value we store must be traceable to a page we actually
read:

  * Genre is only assigned when a term from a controlled vocabulary
    appears in the band's own copy (their site, Bandcamp tags, YouTube /
    OG description, schema.org MusicGroup.genre). We never ask a model to
    guess a genre from a band's name — these are real working musicians
    and a wrong label is worse than a blank field.
  * Ratings are only captured when the page states one ("4.9/5 stars",
    "4.9 out of 5", "Rated 5 stars"). We record the number *and* the URL
    it came from so the UI can attribute it. We do not compute, average,
    or estimate ratings.

Facebook and Instagram are deliberately not read. Both serve a login wall
to unauthenticated clients, so there is no copy to extract, and working
around that wall would breach their terms. Those links stay in the UI as
buttons; for venues and acts that only post to social, the flyer-image
ingest (services/calendar_image_extract.py) is the supported path.

Anything we can't source is left null for an admin to fill in.

Usage:
    python scripts/enrich_band_genres.py --dry-run          # report only
    python scripts/enrich_band_genres.py --out seed.json    # write seed
    python scripts/enrich_band_genres.py --apply            # write to DB
    python scripts/enrich_band_genres.py --limit 20         # sample first
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Run as `python scripts/enrich_band_genres.py` from api/ — put the package
# root on the path so `database` / `models` resolve in the --apply path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("enrich_bands")

TIMEOUT = 20
# Below this, a page is JS-rendered or image-only rather than mislinked.
MIN_READABLE_CHARS = 80
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/127.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "lib"

# Controlled vocabulary. Key = canonical label we display; value = regexes
# that must appear in the band's own copy for us to claim it. Ordered
# roughly specific -> general so "classic rock" wins over "rock".
GENRE_TERMS: list[tuple[str, str]] = [
    ("Classic Rock",      r"\bclassic rock\b"),
    ("Yacht Rock",        r"\byacht rock\b"),
    ("Southern Rock",     r"\bsouthern rock\b"),
    ("Punk",              r"\bpunk\b|\bpop[- ]punk\b"),
    ("Metal",             r"\bmetal\b|\bhard rock\b"),
    ("Alternative",       r"\balternative\b|\balt[- ]rock\b|\bgrunge\b"),
    ("Indie",             r"\bindie\b"),
    ("Rock",              r"\brock\b|\brock ?n ?roll\b|\brock and roll\b"),
    ("Blues",             r"\bblues\b"),
    ("Jazz",              r"\bjazz\b|\bbebop\b|\bswing\b"),
    ("Funk",              r"\bfunk\b|\bfunky\b"),
    ("Soul",              r"\bsoul\b|\bmotown\b|\br ?& ?b\b|\brhythm and blues\b"),
    ("Reggae",            r"\breggae\b|\bska\b|\bdub\b"),
    ("Country",           r"\bcountry\b|\bhonky[- ]tonk\b"),
    ("Americana",         r"\bamericana\b|\broots rock\b"),
    ("Bluegrass",         r"\bbluegrass\b"),
    ("Folk",              r"\bfolk\b"),
    ("Singer-Songwriter", r"\bsinger[- ]songwriter\b"),
    ("Acoustic",          r"\bacoustic\b|\bunplugged\b"),
    ("Jam Band",          r"\bjam band\b|\bjamband\b"),
    ("Hip Hop",           r"\bhip[- ]hop\b|\brap\b"),
    ("Pop",               r"\bpop\b(?![- ]punk)"),
    ("Dance",             r"\bdance\b|\bhouse music\b|\bedm\b|\bdisco\b"),
    ("DJ",                r"\bdj\b|\bdeejay\b|\bturntabl"),
    ("Tribute",           r"\btribute\b"),
    ("Cover Band",        r"\bcover band\b|\bcover songs\b|\bcovers\b|\btop 40\b"),
    ("80s",               r"\b80s\b|\b1980s\b|\beighties\b"),
    ("90s",               r"\b90s\b|\b1990s\b|\bnineties\b"),
    ("Irish",             r"\birish\b|\bceltic\b"),
    ("Latin",             r"\blatin\b|\bsalsa\b|\bbachata\b"),
]

# "4.9/5", "4.9 out of 5", "rated 4.9 stars", "5 star"
RATING_RES = [
    re.compile(r"(\d(?:\.\d)?)\s*/\s*5\b"),
    re.compile(r"(\d(?:\.\d)?)\s*out of\s*5\b", re.I),
    re.compile(r"rated\s*(\d(?:\.\d)?)\s*(?:stars?|/\s*5)", re.I),
    re.compile(r"(\d(?:\.\d)?)\s*star rating\b", re.I),
]
REVIEW_COUNT_RE = re.compile(r"\(?\s*(\d[\d,]*)\s*\+?\s*(?:reviews?|ratings?)\s*\)?", re.I)


# ── Source inventory ──────────────────────────────────────────────────

def parse_known_band_links(path: Path) -> dict[str, dict[str, str]]:
    """Pull the KNOWN record out of knownBandLinks.ts.

    A regex parse rather than a JS eval: the file is a flat
    `"key": { field: "url", ... }` map and has stayed that shape since it
    was seeded. If it ever gains nesting this returns fewer entries rather
    than wrong ones, and the caller logs the count.
    """
    src = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    block_re = re.compile(r'"([^"]+)"\s*:\s*\{(.*?)\n  \}', re.S)
    field_re = re.compile(r'(\w+)\s*:\s*"([^"]+)"')
    for m in block_re.finditer(src):
        name, body = m.group(1), m.group(2)
        fields = {k: v for k, v in field_re.findall(body) if k != "aliases"}
        if fields:
            out[name.lower()] = fields
    return out


def parse_band_guide(path: Path) -> dict[str, dict]:
    """Genre tags already curated in bandGuide.ts — free, no fetch needed."""
    src = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for m in re.finditer(r'name:\s*"([^"]+)",\s*rating:\s*(\d)', src):
        name = m.group(1)
        seg = src[m.end():m.end() + 1200]
        tags_m = re.search(r'tags:\s*\[([^\]]*)\]', seg)
        tags = re.findall(r'"([^"]+)"', tags_m.group(1)) if tags_m else []
        out[name.lower()] = {"tags": tags}
    return out


def act_names_from_api(base: str) -> list[str]:
    url = f"{base.rstrip('/')}/api/calendar/events?upcoming_only=true&limit=500"
    data = requests.get(url, timeout=30).json()
    names = {e["title"].strip() for e in data
             if e.get("event_type") == "live_music" and e.get("title")}
    return sorted(names)


def act_names_from_db() -> list[str]:
    from sqlalchemy import text
    from database import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT DISTINCT title FROM calendar_events "
            "WHERE event_type = 'live_music' AND date >= CURRENT_DATE"
        )).fetchall()
        return sorted(r.title.strip() for r in rows if r.title)
    finally:
        db.close()


# ── Extraction ────────────────────────────────────────────────────────

def _name_variants(n: str) -> set[str]:
    b = n.strip().lower()
    out = {b, re.sub(r"^the\s+", "", b)}
    out |= {re.sub(r"\s+(band|trio|duo|quartet|solo|project)$", "", x) for x in set(out)}
    return {x.strip() for x in out if x.strip()}


def harvest_text(url: str) -> tuple[str, str, Optional[str]]:
    """Fetch a page and return (searchable_text, raw_html, error).

    We concatenate only the fields a band controls and that describe the
    act: title, meta description/keywords, OG description, schema.org
    genre, Bandcamp tag links, and headings. Deliberately NOT the whole
    page body — a footer that says "rock" in an unrelated sentence
    shouldn't brand the act.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return "", "", f"HTTP {r.status_code}"
    except Exception as exc:
        return "", "", f"{type(exc).__name__}"

    soup = BeautifulSoup(r.text, "html.parser")
    parts: list[str] = []

    if soup.title and soup.title.string:
        parts.append(soup.title.string)
    for attr, key in (("name", "description"), ("name", "keywords"),
                      ("property", "og:description"), ("property", "og:title")):
        for tag in soup.find_all("meta", attrs={attr: key}):
            if tag.get("content"):
                parts.append(tag["content"])
    # schema.org MusicGroup / MusicRecording genre
    for tag in soup.find_all(attrs={"itemprop": "genre"}):
        parts.append(tag.get_text(" ", strip=True) or tag.get("content", ""))
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            blob = json.loads(script.string or "{}")
        except Exception:
            continue
        for obj in (blob if isinstance(blob, list) else [blob]):
            if isinstance(obj, dict) and obj.get("genre"):
                g = obj["genre"]
                parts.extend(g if isinstance(g, list) else [str(g)])
    # Bandcamp genre tags
    for a in soup.select("a.tag, a.tralbum-tags, .tralbumData.tralbum-tags a"):
        parts.append(a.get_text(" ", strip=True))
    for h in soup.find_all(["h1", "h2", "h3"])[:12]:
        parts.append(h.get_text(" ", strip=True))

    return " \n ".join(p for p in parts if p), r.text, None


def page_is_about_act(text: str, name: str) -> bool:
    """Does this page actually appear to be about the act we looked up?

    knownBandLinks.ts is hand-curated and occasionally points at the wrong
    band — "Brendan Brophy" mapped to enjoytheband.com, which belongs to a
    different act called "enjoy!". Without this check we'd label a real
    musician with another band's genre and cite a source that never
    mentions them.

    A loose containment test on the act's name (or a variant with "The"
    / "Trio" / "Duo" stripped) against the page's own title, headings and
    meta description. Cheap, and it fails closed: an unverifiable page
    contributes nothing rather than something wrong.
    """
    low = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    low = re.sub(r"\s+", " ", low)
    # Also compare with everything but letters and digits removed, so a
    # page whose only self-identification is its domain still counts:
    # quincymumford.com never contains "quincy mumford" with the space,
    # and the spaced check alone flagged the artist's own site as a
    # mislink. Require 6 characters there so a short squashed name can't
    # collide with the middle of an unrelated word.
    squashed = re.sub(r"[^a-z0-9]+", "", text.lower())
    for v in _name_variants(name):
        spaced = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", v)).strip()
        if len(spaced) >= 4 and spaced in low:
            return True
        tight = re.sub(r"[^a-z0-9]+", "", v)
        if len(tight) >= 6 and tight in squashed:
            return True
    return False


# Discovery: acts with no curated link get nothing, and that's most of
# them. Local acts overwhelmingly sit on {name}.com / {name}band.com /
# {name}music.com, so those are worth trying — brotherpeteband.com is
# exactly that shape.
#
# The catch is that guessing a domain FROM a name makes the usual name
# check circular: the domain appears in the page title, so it "verifies"
# itself. Guessing alone matched a Venice Beach skateboard company for
# Rocketfish and Anthony Skincare For Men for Anthony². So a guessed
# domain must also read like a local musician's page — music vocabulary
# AND a New Jersey reference — before we'll believe it. That drops 31
# candidates to 8, which is the right trade when the cost of a false
# positive is publishing a stranger's website under a working musician's
# name.
_MUSIC_CTX = re.compile(
    r"\b(band|live music|gig|setlist|tour dates|album|singer|guitarist|"
    r"drummer|vocalist|booking|shows?|music|acoustic|rock|blues|country)\b", re.I)
_LOCAL_CTX = re.compile(
    r"\b(new jersey|nj\b|jersey shore|monmouth|asbury|highlands|sea bright|"
    r"red bank|belmar|point pleasant|shore)\b", re.I)

# Event titles that name an activity, not an act. A band page for these
# would be meaningless and the domains ARE real businesses (karaoke.com).
GENERIC_TITLES = {
    "karaoke", "open mic night", "open mic", "trivia", "dj", "live music",
    "tba", "tbd", "dueling pianos", "bingo", "happy hour",
}


def domain_candidates(name: str) -> list[str]:
    squashed = re.sub(r"[^a-z0-9]+", "", name.lower())
    if len(squashed) < 5:
        return []                      # too short to guess safely
    base = re.sub(r"^the", "", squashed)
    out: list[str] = []
    for stem in dict.fromkeys([squashed, base]):
        out += [f"{stem}.com", f"{stem}band.com", f"{stem}music.com"]
    return list(dict.fromkeys(out))[:6]


def discover_website(name: str) -> Optional[str]:
    """Guess an act's website, returning it only if the page corroborates."""
    if name.strip().lower() in GENERIC_TITLES:
        return None
    for host in domain_candidates(name):
        url = f"https://www.{host}"
        text, raw_html, err = harvest_text(url)
        if err or not text:
            continue
        if not page_is_about_act(text, name):
            continue
        soup = BeautifulSoup(raw_html or "", "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        corpus = f"{text} {soup.get_text(' ', strip=True)[:8000]}"
        if _MUSIC_CTX.search(corpus) and _LOCAL_CTX.search(corpus):
            return url
    return None


_YT_RE = re.compile(
    r"(?:https?:)?//(?:www\.)?(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)"
    r"|youtu\.be/)([A-Za-z0-9_-]{11})")


def youtube_video_on_page(html: str) -> Optional[str]:
    """First embedded YouTube video on a band's own page.

    Most of the YouTube links we hold are channel URLs (/@handle, /user/…)
    that can't be embedded without an API lookup. Bands do, however, tend
    to embed a video on their own site — that iframe src is a real video
    id we can use directly.

    Takes the first match: on a band site the lead video is the one at the
    top, and picking arbitrarily among later ones would be worse than
    letting an admin override it.
    """
    m = _YT_RE.search(html or "")
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None


def genres_from_text(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for label, pattern in GENRE_TERMS:
        if re.search(pattern, low):
            found.append(label)
    # Drop the generic parent when a more specific sibling matched.
    if any(g in found for g in ("Classic Rock", "Yacht Rock", "Southern Rock",
                                "Punk", "Metal", "Alternative", "Indie")):
        found = [g for g in found if g != "Rock"]
    return found[:6]


def rating_from_text(text: str) -> tuple[Optional[float], Optional[int]]:
    for rx in RATING_RES:
        m = rx.search(text)
        if m:
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            if 0 < val <= 5:
                cm = REVIEW_COUNT_RE.search(text)
                count = int(cm.group(1).replace(",", "")) if cm else None
                return val, count
    return None, None


def enrich_one(name: str, links: dict[str, str], guide_tags: list[str],
               discover: bool = False) -> dict:
    """Read every source we have for one act and merge what they state."""
    result = {
        "name": name,
        "genres": [],
        "genre_sources": [],
        "rating": None,
        "rating_count": None,
        "rating_source_url": None,
        "video_url": None,
        "video_source_url": None,
        "checked": [],
        "errors": [],
        "needs_review": False,
        "discovered_website": None,
    }
    if discover and not links.get("website"):
        found_site = discover_website(name)
        if found_site:
            links = {**links, "website": found_site}
            result["discovered_website"] = found_site

    if guide_tags:
        result["genres"] = list(guide_tags)
        result["genre_sources"].append("bandGuide.ts (curated)")

    # Order matters: a band's own site and Bandcamp state genre most
    # reliably; a YouTube channel description is noisier but usable.
    #
    # Instagram and Facebook are skipped outright — both serve a login wall
    # to anything without a session, so they yield no readable copy. We
    # keep the links for the "Find them online" buttons, but there is
    # nothing here to read. (See the FB/IG note in the module docstring.)
    for field in ("bandcamp", "website", "youtube", "bandsintown"):
        url = links.get(field)
        if not url:
            continue
        text, raw_html, err = harvest_text(url)
        result["checked"].append(field)
        if err:
            result["errors"].append(f"{field}: {err}")
            continue
        if not page_is_about_act(text, name):
            # Can't confirm the page is this act's. Thin pages get the
            # benefit of the doubt — a JS-rendered or image-only site has
            # nothing to identify itself with, so calling it a mislink
            # would be wrong. A substantive page that still never names the
            # act is a genuinely bad curated link.
            if len(text.strip()) < MIN_READABLE_CHARS:
                result["errors"].append(f"{field}: too little readable text ({url})")
            else:
                result["errors"].append(f"{field}: page does not mention the act ({url})")
                result["needs_review"] = True
            continue

        # Confirmed this act's page — take whatever it offers, however
        # sparse. The thin-text test used to run first and skip the whole
        # page, which cost us videos: nedryersonlive.com identifies itself
        # and embeds a YouTube video, but harvests only 76 characters of
        # title/meta/heading text and so was dropped before we ever looked
        # for the iframe. Text volume gates the genre read, not the page.
        if result["video_url"] is None:
            vid = youtube_video_on_page(raw_html)
            if vid:
                result["video_url"] = vid
                result["video_source_url"] = url

        found = genres_from_text(text)
        if found:
            for g in found:
                if g not in result["genres"]:
                    result["genres"].append(g)
            result["genre_sources"].append(url)
        if result["rating"] is None:
            val, count = rating_from_text(text)
            if val is not None:
                result["rating"] = val
                result["rating_count"] = count
                result["rating_source_url"] = url

    result["genres"] = result["genres"][:6]
    return result


# ── Entry point ───────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=None,
                    help="read act names from this API base instead of the DB")
    ap.add_argument("--out", default=None, help="write results as JSON here")
    ap.add_argument("--apply", action="store_true", help="write results to band_profiles")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N acts")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--discover", action="store_true",
                    help="guess websites for acts with no curated link "
                         "(corroborated; see discover_website)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    known = parse_known_band_links(WEB_DIR / "knownBandLinks.ts")
    guide = parse_band_guide(WEB_DIR / "bandGuide.ts")
    logger.info("known-links entries: %d | guide entries: %d", len(known), len(guide))

    names = act_names_from_api(args.api) if args.api else act_names_from_db()
    if args.limit:
        names = names[:args.limit]
    logger.info("acts to enrich: %d", len(names))

    def lookup(table: dict, name: str):
        for v in _name_variants(name):
            if v in table:
                return table[v]
        return None

    jobs = []
    for n in names:
        links = lookup(known, n) or {}
        g = lookup(guide, n) or {}
        jobs.append((n, links, g.get("tags", [])))

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda a: enrich_one(*a, discover=args.discover), jobs))

    with_genre = [r for r in results if r["genres"]]
    with_rating = [r for r in results if r["rating"] is not None]
    no_source = [r for r in results if not r["checked"] and not r["genres"]]

    logger.info("")
    logger.info("=== results ===")
    logger.info("acts with genre:  %d / %d", len(with_genre), len(results))
    logger.info("acts with rating: %d / %d (sourced only)", len(with_rating), len(results))
    disc = [r for r in results if r.get("discovered_website")]
    if disc:
        logger.info("")
        logger.info("discovered %d website(s) — review before trusting:", len(disc))
        for r in disc:
            logger.info("   %-26s %s", r["name"][:26], r["discovered_website"])
        logger.info("")
    logger.info("acts with a video:  %d / %d", sum(1 for r in results if r.get("video_url")), len(results))
    logger.info("acts with no source to read at all: %d", len(no_source))
    mislinked = [r for r in results if r.get("needs_review")]
    if mislinked:
        logger.info("")
        logger.info("!! %d act(s) whose curated link never names them — fix "
                    "knownBandLinks.ts:", len(mislinked))
        for r in mislinked:
            for e in r["errors"]:
                if "does not mention" in e:
                    logger.info("   %-28s %s", r["name"][:28], e)
    logger.info("")
    for r in sorted(with_genre, key=lambda x: x["name"]):
        src = r["genre_sources"][0] if r["genre_sources"] else "?"
        rating = f"  [{r['rating']}/5 from {r['rating_source_url']}]" if r["rating"] else ""
        logger.info("  %-32s %s%s", r["name"][:32], ", ".join(r["genres"]), rating)
        logger.info("  %-32s   src: %s", "", src)

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        logger.info("\nwrote %s", args.out)

    if args.apply:
        written = write_to_db(results)
        logger.info("\nwrote %d band_profiles rows", written)
    return 0


def write_to_db(results: list[dict]) -> int:
    from database import SessionLocal
    from models.band_profile import BandProfile

    db = SessionLocal()
    written = 0
    try:
        for r in results:
            if (not r["genres"] and r["rating"] is None
                    and not r.get("video_url") and not r.get("discovered_website")):
                continue
            key = r["name"].strip().lower()
            row = db.query(BandProfile).filter(BandProfile.name_lower == key).one_or_none()
            if row is None:
                row = BandProfile(name=r["name"].strip(), name_lower=key)
                db.add(row)
            # Never clobber an admin's hand-entered value with a scraped one.
            if r["genres"] and not row.genres:
                row.genres = ", ".join(r["genres"])
                row.genre_source_url = next(
                    (s for s in r["genre_sources"] if s.startswith("http")), None)
            if r.get("video_url") and not row.video_url:
                row.video_url = r["video_url"]
            # A discovered site was only used to read from; store it too, or
            # the band page has no "Website" button for an act whose site we
            # just proved we can find. Curated links already render from
            # knownBandLinks, so this only fills genuine gaps.
            if r.get("discovered_website") and not row.website_url:
                row.website_url = r["discovered_website"]
            if r["rating"] is not None and row.rating is None:
                row.rating = r["rating"]
                row.rating_count = r["rating_count"]
                row.rating_source_url = r["rating_source_url"]
            written += 1
        db.commit()
    finally:
        db.close()
    return written


if __name__ == "__main__":
    sys.exit(main())
