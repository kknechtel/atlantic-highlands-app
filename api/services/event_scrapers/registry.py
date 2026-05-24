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
from . import squarespace, html_parse, bandsintown, playwright_adapter

# Re-export the html-parse parsers we use from Playwright too, so the
# registry kwargs read cleanly without long dotted imports.
_parse_sandbox = html_parse.parse_sandbox

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
        # 2026-05-24: switched to playwright-paginated. The static HTML
        # only contains the CURRENT week (future weeks are JS-loaded on
        # click). We click `span.week-next` 12 times to cover ~3 months.
        # Bandsintown has the full season but Cloudflare-blocks our EC2
        # IPs (residential proxy required), so this is the practical path.
        "The Sandbox at Seastreak", "Highlands",
        playwright_adapter.fetch_events_paginated,
        {
            "url": "https://sandbox.seastreak.com/",
            "parser": _parse_sandbox,
            "next_selector": "span.week-next",
            "steps": 12,
            "wait_between_ms": 1200,
            "wait_for_selector": "div.event",
        },
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
    # ── Playwright (JS-rendered venue pages) ──────────────────────
    (
        "The Chubby Pickle", "Highlands",
        playwright_adapter.fetch_events,
        # JetEngine grid widget renders events client-side.
        {"url": "https://thechubbypicklenj.com/calendar/",
         "parser": playwright_adapter.parse_chubby_pickle_dom,
         "wait_for_selector": ".jet-listing-grid__item, .jet-listing-grid-item"},
    ),
    (
        "Donovan's Reef", "Sea Bright",
        playwright_adapter.fetch_events,
        # BeatGig embed script injects events client-side.
        {"url": "https://www.donovansreefbeachbar.com/calendar",
         "parser": playwright_adapter.parse_donovans_dom,
         "wait_for_selector": 'div[class*="bg-event"], .beatgig-event'},
    ),
    # ── Deferred (no scrape path that's realistic from EC2) ───────
    # Off the Hook                  Squarespace events collection empty
    # Barnacle Bill's (Rumson/SB)   Live-music page is static text, no calendar
    # Eventide Grille               Schedule on Facebook only
    # McLoone's Rum Runner          /entertainment.php returns 403 to bot UAs
    # Tommy's Tavern + Tap          Chain site; FB only
    # Wine Bar / Atlantic House     Static sites; FB only
    # Copper Canyon @ Blue Bay Inn  Static site; FB only
    # Bandsintown (Sandbox full season)  Cloudflare-blocked from EC2 IPs
    # All of the above are candidates for the crowdsourced-submission /
    # FB-pipeline approach (see FB/IG plan doc).
]
