"""The town this deployment serves.

Everything specific to one municipality (its name, the sites the scraper
reads, the governments its documents come from, the background the AI is
given) lives in municipalities/<slug>/ at the repo root:

  profile.json   identity, entities, map, contact (see municipalities/README.md)
  sources.json   what the scraper crawls: {"documents": {...}, "recordings": {...}}
  context.md     background facts and analysis notes for the AI

MUNICIPALITY picks the folder (default atlantic-highlands-nj);
MUNICIPALITY_DIR points somewhere else entirely (e.g. a Docker mount).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent / "municipalities"


def folder() -> Path:
    explicit = os.environ.get("MUNICIPALITY_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return _ROOT / os.environ.get("MUNICIPALITY", "atlantic-highlands-nj").strip()


def _read_json(name: str) -> dict:
    path = folder() / name
    if not path.exists():
        raise RuntimeError(
            f"Municipality file missing: {path}. Set MUNICIPALITY to a folder under "
            f"municipalities/ (copy municipalities/example to start)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def profile() -> dict:
    return _read_json("profile.json")


@lru_cache(maxsize=1)
def sources() -> dict:
    return _read_json("sources.json")


@lru_cache(maxsize=1)
def context() -> str:
    """context.md for the AI, without its title line and <!-- notes -->."""
    path = folder() / "context.md"
    if not path.exists():
        return ""
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"\A\s*# [^\n]*\n", "", text)
    return text.strip()


def entities() -> list[dict]:
    return profile().get("entities", [])


def entity_ids() -> list[str]:
    return [e["id"] for e in entities()]


def primary_entity() -> dict:
    ents = entities()
    return next((e for e in ents if e.get("primary")), ents[0] if ents else {"id": "town", "label": profile()["official_name"], "short": profile()["name"]})


def entity(entity_id: str | None) -> dict | None:
    return next((e for e in entities() if e["id"] == entity_id), None)


def entity_for_source(source_name: str) -> str:
    """The government that published a scraper source's records."""
    for group in sources().values():
        if source_name in group:
            return group[source_name].get("entity") or primary_entity()["id"]
    return primary_entity()["id"]


def place() -> str:
    """'Atlantic Highlands, NJ' — the town as people write it."""
    p = profile()
    return f"{p['name']}, {p['state']}"


# Attribute access for the common fields: TOWN.name, TOWN.official_name, ...
class _Town(SimpleNamespace):
    def __getattr__(self, item):
        try:
            return profile()[item]
        except KeyError:
            raise AttributeError(item) from None


TOWN = _Town()
