"""Per-venue live-music scrapers.

Two adapters cover the bulk of the live-music venues across the towns in
the profile's events_area:

  - squarespace.fetch_events  — Squarespace events collection JSON
  - tribe_events.fetch_events  — WordPress "The Events Calendar" REST

The `registry` lists each venue with its adapter + URL. `runner.run_music_scrape`
iterates the registry, isolates failures per venue, and persists results
to `calendar_events` with event_type='live_music'.
"""
from .runner import run_music_scrape

__all__ = ["run_music_scrape"]
