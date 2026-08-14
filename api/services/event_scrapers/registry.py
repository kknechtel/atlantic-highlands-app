"""Live-music venue registry — one entry per scrapeable venue.

Each entry: (display_name, city, adapter_callable, adapter_kwargs).

If a URL breaks (site redesign etc.) the runner logs and continues
with the others, so a single dead venue can't take out the whole
nightly run.

v3 status (2026-08-14) — audited every venue against its live site:
  - Healthy: Proving Ground, Sandbox at Seastreak, Chubby Pickle
    (playwright), Donovan's Reef, Seafarer, Drifthouse
  - Seafarer was silently down to ~1 event/season. It still publishes a
    full lineup; parse_seafarer was picking the wrong homepage block.
    Fixed by selecting on date-line density — see that parser.
  - Drifthouse moved to the Playwright adapter: the site now 403s plain
    requests. Same parser, browser-rendered fetch.
  - Chubby Pickle's WP-REST entry dropped — it 403s now, and the
    playwright entry already covers the same venue.
  - On the Deck dropped — see Deferred below.

v2 notes still in force:
  - Squarespace adapter uses `?format=json-pretty` + `upcoming[]`
  - WordPress Tribe Events adapter is unused (no venue actually exposes it)
  - Both squarespace and bandsintown are imported but currently unused by
    VENUES; kept so venues can be re-added without hunting the adapter.
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
    # ── Playwright (JS-rendered / bot-blocked venue pages) ────────
    (
        # 2026-08-14: drifthousenj.com started returning 403 to plain
        # requests regardless of User-Agent. The page itself is unchanged
        # and parse_drifthouse still works against it, so we just render it
        # through a real browser instead of dropping the venue.
        "Drifthouse by David Burke", "Sea Bright",
        playwright_adapter.fetch_events,
        {"url": "https://drifthousenj.com/events/",
         "parser": html_parse.parse_drifthouse,
         "wait_for_selector": None},
    ),
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
    # On the Deck (Atlantic Highlands)  2026-08-14: /live-music is a 404 and
    #                               the site no longer publishes a schedule
    #                               anywhere — the replacement "Happening
    #                               @OTD" page is a single flyer image. This
    #                               is our only AH venue, so it's the best
    #                               candidate for the calendar-image ingest
    #                               (services/calendar_image_extract.py).
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
