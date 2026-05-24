"""Live-music venue registry — one entry per scrapeable venue.

Each entry: (display_name, city, adapter_callable, adapter_kwargs).

The 7 venues below cover the highest-volume live-music rooms in
Atlantic Highlands, Highlands, and Sea Bright. Facebook-only spots
(Bahrs, Gaslight, Inlet, etc.) are deliberately omitted — adding
the FB Graph integration would require app review for permissions
that are over-scoped for this use case.

If a URL breaks (site redesign etc.) the runner logs and continues
with the others, so a single dead venue can't take out the whole
nightly run.
"""
from . import squarespace, tribe_events

# Each tuple's adapter_kwargs are spread into the adapter's signature.
# Add new venues by appending a tuple — no other code touched.
VENUES = [
    # ── Highlands ─────────────────────────────────────────────────
    (
        "The Proving Ground", "Highlands",
        squarespace.fetch_events,
        {"collection_url": "https://www.theprovingground.com/events"},
    ),
    (
        "The Chubby Pickle", "Highlands",
        tribe_events.fetch_events,
        {"site_base": "https://thechubbypicklenj.com"},
    ),
    (
        "Off the Hook", "Highlands",
        squarespace.fetch_events,
        {"collection_url": "https://offthehookhighlands.com/events"},
    ),
    (
        "The Seafarer", "Highlands",
        squarespace.fetch_events,
        # Seafarer uses a homepage schedule — try the common `/events` slug
        # first; if empty we'll iterate to a different collection on the
        # next deploy after inspecting their site source.
        {"collection_url": "https://www.seafarernj.com/events"},
    ),
    (
        "The Sandbox at Seastreak", "Highlands",
        tribe_events.fetch_events,
        {"site_base": "https://sandbox.seastreak.com"},
    ),
    # ── Atlantic Highlands ────────────────────────────────────────
    (
        "On the Deck", "Atlantic Highlands",
        squarespace.fetch_events,
        {"collection_url": "https://www.onthedeckrestaurant.com/live-music"},
    ),
    # ── Sea Bright ────────────────────────────────────────────────
    (
        "Donovan's Reef", "Sea Bright",
        squarespace.fetch_events,
        {"collection_url": "https://www.donovansreefbeachbar.com/calendar"},
    ),
]
