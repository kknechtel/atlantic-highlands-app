#!/usr/bin/env python3
"""
NJ Daniel's Law (P.L. 2020 c.125) backfill: NULL out owner identity columns
on every parcels row sourced from a bulk MOD-IV feed, and strip the same
keys from each row's raw_attrs JSONB.

Idempotent — safe to run repeatedly. Reports row counts so the SSM operator
can confirm what changed.

Usage (locally):
    DATABASE_URL=...  python -m scripts.backfill_daniels_law_redaction

Usage (prod, via SSM):
    sudo -u atlantic-highlands /opt/atlantic-highlands/venv/bin/python \\
        -m scripts.backfill_daniels_law_redaction
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from database import SessionLocal

logger = logging.getLogger("backfill_daniels_law")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Match any bulk MOD-IV provenance label written by scripts.ingest_parcels.
BULK_SOURCE_LIKE = "NJGIN_MOD-IV_%"

# Same redaction set as scripts.ingest_parcels._OWNER_REDACT_KEYS; kept inline
# here so this script can run standalone on prod without import cycles.
OWNER_REDACT_KEYS = [
    "OWNER_NAME", "OWNERS_NAME", "OWNER", "OWN_NAME",
    "ST_ADDRESS", "OWNERS_STREET", "OWN_STREET",
    "CITY_STATE", "OWNERS_CITY_STATE_ZIP", "OWN_CSZ",
]


def main() -> None:
    db = SessionLocal()
    try:
        before = db.execute(text(
            "SELECT COUNT(*) FROM parcels "
            "WHERE (owner_name IS NOT NULL OR owner_street IS NOT NULL OR owner_city_state_zip IS NOT NULL) "
            "  AND data_source LIKE :pat"
        ), {"pat": BULK_SOURCE_LIKE}).scalar() or 0
        logger.info(f"rows with owner_* set from bulk source: {before}")

        # Column-level NULL.
        res_cols = db.execute(text(
            "UPDATE parcels "
            "SET owner_name = NULL, owner_street = NULL, owner_city_state_zip = NULL "
            "WHERE data_source LIKE :pat "
            "  AND (owner_name IS NOT NULL OR owner_street IS NOT NULL OR owner_city_state_zip IS NOT NULL)"
        ), {"pat": BULK_SOURCE_LIKE})
        logger.info(f"NULLed owner_* columns on {res_cols.rowcount} rows")

        # JSONB key strip. Postgres `jsonb - text[]` removes top-level keys.
        res_json = db.execute(text(
            "UPDATE parcels "
            "SET raw_attrs = raw_attrs - CAST(:keys AS text[]) "
            "WHERE data_source LIKE :pat "
            "  AND raw_attrs ?| CAST(:keys AS text[])"
        ), {"pat": BULK_SOURCE_LIKE, "keys": OWNER_REDACT_KEYS})
        logger.info(f"stripped owner keys from raw_attrs on {res_json.rowcount} rows")

        db.commit()

        remaining = db.execute(text(
            "SELECT COUNT(*) FROM parcels "
            "WHERE (owner_name IS NOT NULL OR owner_street IS NOT NULL OR owner_city_state_zip IS NOT NULL) "
            "  AND data_source LIKE :pat"
        ), {"pat": BULK_SOURCE_LIKE}).scalar() or 0
        logger.info(f"rows still carrying owner_* from bulk source after redaction: {remaining}")
        if remaining:
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
