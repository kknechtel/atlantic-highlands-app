#!/usr/bin/env python3
"""
One-shot backfill: extract the building/land characteristic fields that
are already sitting in parcels.raw_attrs (from the NJGIN composite) into
their own columns, so the API can return them without parsing JSONB.

Covers:
  building_description  <- raw_attrs.BLDG_DESC   ("1STFLR-3/1/1" etc.)
  dwelling_units        <- raw_attrs.DWELL       (integer)
  land_description      <- raw_attrs.LAND_DESC   ("50X130" dimensions or "C.E.=" condo equity)
  property_use          <- raw_attrs.PROP_USE
  zip5                  <- raw_attrs.ZIP5

Idempotent — re-running just rewrites the same values.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.parcel import Parcel


def _clean(v):
    """Treat null-ish JSONB values as None."""
    if v in (None, "", "null", "None"):
        return None
    return v


def _to_int(v):
    v = _clean(v)
    if v is None:
        return None
    try:
        n = int(float(v))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def main():
    db = SessionLocal()
    updated = 0
    total = 0
    try:
        parcels = db.query(Parcel).all()
        for p in parcels:
            total += 1
            attrs = p.raw_attrs or {}

            new_vals = dict(
                building_description=_clean(attrs.get("BLDG_DESC")),
                dwelling_units=_to_int(attrs.get("DWELL")),
                land_description=_clean(attrs.get("LAND_DESC")),
                property_use=_clean(attrs.get("PROP_USE")),
                zip5=_clean(attrs.get("ZIP5")),
            )

            # Only write if at least one field has a value AND something changed
            dirty = False
            for k, v in new_vals.items():
                if v is not None and getattr(p, k) != v:
                    setattr(p, k, v)
                    dirty = True
            if dirty:
                updated += 1

            if total % 500 == 0:
                db.commit()
                print(f"  committed at {total}/{len(parcels)} (updated={updated})", flush=True)

        db.commit()
        print(f"\nDone. Updated {updated}/{total} parcels.")

        # Coverage summary
        from sqlalchemy import func
        for col in ("building_description", "dwelling_units", "land_description", "property_use", "zip5"):
            n = db.query(func.count()).filter(getattr(Parcel, col).isnot(None)).scalar()
            print(f"  {col:<22}  {n} / {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
