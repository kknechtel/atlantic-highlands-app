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
from . import squarespace, html_parse, bandsintown

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
    (
        "The Sandbox at Seastreak", "Highlands",
        html_parse.fetch_events,
        # Homepage only (~current week). Their own ?week=YYYY-MM-DD does
        # not change the rendered HTML (verified). Bandsintown has the
        # full season but is Cloudflare-blocked from EC2 (HTTP 403
        # regardless of UA — residential proxy needed). So we accept the
        # 1-week ceiling and pick up new shows as the date rolls forward.
        {"url": "https://sandbox.seastreak.com/",
         "parser": html_parse.parse_sandbox},
    ),
    # ── Atlantic Highlands ────────────────────────────────────────
    (
        "On the Deck", "Atlantic Highlands",
        squarespace.fetch_events,
        {"collection_url": "https://www.onthedeckrestaurant.com/live-music"},
    ),
    # ── Sea Bright ────────────────────────────────────────────────
    (
        "Drifthouse by David Burke", "Sea Bright",
        html_parse.fetch_events,
        {"url": "https://drifthousenj.com/events/",
         "parser": html_parse.parse_drifthouse},
    ),
    # ── Deferred (HTML scraping not viable) ───────────────────────
    # Off the Hook                  Squarespace events collection empty
    # Donovan's Reef                BeatGig client-side embed → Playwright
    # The Chubby Pickle             JetEngine widget; events JS-rendered
    # Barnacle Bill's (Rumson/SB)   Live-music page is static text, no calendar
    # Eventide Grille               Schedule on Facebook only
    # McLoone's Rum Runner          /entertainment.php returns 403 to bot UAs
    # Tommy's Tavern + Tap          Chain site; FB only
    # Wine Bar / Atlantic House     Static sites; FB only
    # Copper Canyon @ Blue Bay Inn  Static site; FB only
    # All of the above are candidates for the future
    # crowdsourced-submission / FB-pipeline approach.
]
