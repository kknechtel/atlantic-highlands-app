"""Live-music venue registry — one entry per scrapeable venue.

Each entry: (display_name, city, adapter_callable, adapter_kwargs).

If a URL breaks (site redesign etc.) the runner logs and continues
with the others, so a single dead venue can't take out the whole
nightly run.

v2 status (2026-05-24):
  - Squarespace adapter rewritten for `?format=json-pretty` + `upcoming[]`
  - WordPress Tribe Events adapter is unused (no venue actually exposes it)
  - New html_parse adapter with per-venue parsers covers Proving Ground,
    Chubby Pickle (via WP REST page render), Seafarer
  - Off the Hook and The Sandbox at Seastreak removed — both publish
    nothing scrapeable. Schedules live on Facebook only. Re-add if a
    Facebook Graph integration ships, or hand-curate via an admin form.
  - Donovan's Reef removed — uses a BeatGig embed that only renders in
    the browser. Needs headless (Playwright) which we don't run in prod.
    Hand-curate or add headless infra later.
"""
from . import squarespace, html_parse

VENUES = [
    # ── Highlands ─────────────────────────────────────────────────
    (
        "The Proving Ground", "Highlands",
        html_parse.fetch_events,
        {"url": "https://www.theprovingground.com/events",
         "parser": html_parse.parse_proving_ground},
    ),
    (
        "The Chubby Pickle", "Highlands",
        html_parse.fetch_events,
        # WP REST returns the calendar page as JSON with pre-rendered HTML.
        {"url": "https://thechubbypicklenj.com/wp-json/wp/v2/pages?slug=calendar",
         "parser": html_parse.parse_chubby_pickle},
    ),
    (
        "The Seafarer", "Highlands",
        html_parse.fetch_events,
        {"url": "https://www.seafarernj.com/",
         "parser": html_parse.parse_seafarer},
    ),
    # ── Atlantic Highlands ────────────────────────────────────────
    (
        "On the Deck", "Atlantic Highlands",
        squarespace.fetch_events,
        {"collection_url": "https://www.onthedeckrestaurant.com/live-music"},
    ),
    # ── Deferred ──────────────────────────────────────────────────
    # Off the Hook            (Squarespace events collection is empty)
    # The Sandbox at Seastreak (WordPress home page only, no event CPT)
    # Donovan's Reef          (BeatGig client-side embed, needs Playwright)
]
