# Municipality profiles

Everything specific to one town lives in a folder here. The code reads the
folder named by `MUNICIPALITY` (default `atlantic-highlands-nj`), or the path in
`MUNICIPALITY_DIR`.

| File | What it holds | Read by |
|---|---|---|
| `profile.json` | Name, state, county, site URL, contact, map, colors, the governments its documents come from (`entities`), records-request contacts (`opra`), search aliases | API (`api/municipality.py`) and the web build (`web/next.config.js`) |
| `sources.json` | What the scraper crawls: `documents` and `recordings` sources | API scraper |
| `context.md` | Background facts and analysis notes given to the AI | API chat and analysis prompts |
| `scripts/` | Optional one-off scripts for that town's data | Run by hand |

## Setting up a new town

1. Copy `example/` to a new folder, e.g. `springfield-il/`.
2. Fill in `profile.json`:
   - `entities`: one entry per government whose records you collect. The one
     with `"primary": true` is the town itself. `kind` is `town`, `school`,
     `regional` or `state`. Each entity's `id` is stored on every document, so
     choose ids once and keep them.
   - `aliases`: the spellings people search with (abbreviations, old names).
   - `opra`: the records custodians. Leave `govpilot_url` empty if the town
     doesn't use GovPilot.
   - `census`: the place's FIPS codes, for demographics.
   - `transcription_terms` (optional): names Whisper mishears in meeting
     recordings: council members, staff, streets, local bodies. Spell them
     exactly as they should appear; Whisper copies these spellings.
3. Fill in `sources.json`: one entry per website. Each source needs
   `base_url`, `description` and `entity`. Then add `pages_to_crawl` (visited
   every run), `historical_pages` (full runs only) and `direct_downloads` (PDFs
   fetched as-is). `crawler` picks the crawler; the default `site` follows
   links on ordinary sites. The others are `pages`, `ecode360`, `edlio`,
   `municode_meetings`, `opramachine`, `census`, `folder_recordings` and
   `youtube_links`. `summary` and `note` are shown on the admin Scraper page.
4. Write `context.md`: the facts a good local analyst would know (form of
   government, officials, school district history, recent controversies), and
   anything that changes how numbers should be read.
5. Set `MUNICIPALITY=<folder>` for the API, the scheduled jobs and the web
   build (Amplify environment variable, or `docker compose` env).
6. Start the app, create an admin (`python api/create_admin.py you@town.org`),
   and enter the API keys under Admin > Settings.

## What isn't in the profile yet

The events app's local data (venues, bands, the music guide, the venue scrapers
in `api/services/event_scrapers/registry.py`) is still written into code for
Atlantic Highlands. A new town should turn the events app off or replace that
data.
