#!/usr/bin/env python3
"""
Ingest Atlantic Highlands parcel records from NJ MOD-IV (Parcels Composite of NJ).

Source: ArcGIS Online "Parcels and MOD-IV Composite of NJ, Web Mercator"
        item id 533599bbfbaa4748bf39faf1375a8a9c
        feature service https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0

Filter: county_code="13" AND muni_code="1303"  (Atlantic Highlands borough, Monmouth)

Field mapping is best-effort; the raw feature attributes are also stored in
parcels.raw_attrs (JSONB) so any field we don't surface is still queryable.

Usage:
    DATABASE_URL=...  python -m scripts.ingest_parcels
    # or with explicit muni filter
    python -m scripts.ingest_parcels --county 13 --muni 1303

Idempotent — uses ON CONFLICT (county, muni, block, lot, qual) DO UPDATE.
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, date
from typing import Iterator, Optional

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.parcel import Parcel

logger = logging.getLogger("ingest_parcels")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

NJ_PARCELS_FS = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu"
    "/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0"
)

# MOD-IV uses these field names (sample). Names vary slightly across snapshots;
# the loader looks up multiple aliases per logical field.
FIELD_ALIASES = {
    "county_code":   ["COUNTY", "CO_CODE", "CO"],
    "muni_code":     ["MUN", "MUN_CODE", "MUNICIPALITY"],
    "block":         ["BLOCK", "BLOCK_"],
    "lot":           ["LOT", "LOT_"],
    "qualifier":     ["QUAL", "QUALIFIER", "QCODE"],
    "pams_pin":      ["PAMS_PIN", "PIN"],
    "property_location": ["PROP_LOC", "PROPLOC", "PROPERTY_LOCATION", "ADDRESS"],
    "property_class":    ["PROP_CLASS", "PROPCLASS", "PROPERTY_CLASS"],
    "owner_name":        ["OWNER_NAME", "OWNERS_NAME", "OWNER"],
    "owner_street":      ["OWNERS_STREET", "OWN_STREET"],
    "owner_city_state_zip": ["OWNERS_CITY_STATE_ZIP", "OWN_CITY_STATE_ZIP", "OWN_CSZ"],
    "land_value":        ["LAND_VAL", "LANDVAL", "LAND_VALUE"],
    "improvement_value": ["IMPRVT_VAL", "IMPRVTVAL", "IMPROVEMENT_VALUE"],
    "total_assessment":  ["TOT_ASSMNT", "NET_VALUE", "ASSESSMENT_TOTAL", "ASSMNT"],
    "tax_amount":        ["LAST_YR_TX", "TAX_AMOUNT"],
    "lot_size_acres":    ["CALC_ACRE", "ACREAGE", "ACRES"],
    "year_built":        ["YR_CONSTR", "YEAR_BUILT", "BLDG_YR"],
    "living_sqft":       ["BLDG_AREA", "LIVING_AREA"],
    "last_sale_date":    ["LST_DEED_D", "LAST_SALE_DATE", "SALE_DATE"],
    "last_sale_price":   ["SALE_PRICE", "LST_SLE_PR"],
    "last_sale_book":    ["BOOK", "DEED_BOOK"],
    "last_sale_page":    ["PAGE", "DEED_PAGE"],
    "last_sale_nu_code": ["NU_CODE", "NU"],
}


def _pick(attrs: dict, key: str):
    """Return the first non-null attribute matching any alias for `key`."""
    for alias in FIELD_ALIASES[key]:
        v = attrs.get(alias)
        if v not in (None, "", "null"):
            return v
    return None


def _to_int(v) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_date(v) -> Optional[date]:
    if v in (None, ""):
        return None
    # ArcGIS returns dates as ms-since-epoch
    try:
        return datetime.utcfromtimestamp(int(v) / 1000).date()
    except (TypeError, ValueError, OSError):
        return None


def fetch_features(county: str, muni: str, page_size: int = 2000) -> Iterator[dict]:
    """Yield feature attribute dicts for the (county, muni) filter, paginated."""
    where = f"COUNTY='{county}' AND MUN='{muni}'"
    offset = 0
    sess = requests.Session()
    sess.headers["User-Agent"] = "ah-app/parcels-ingest"

    while True:
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        for attempt in range(3):
            try:
                r = sess.get(NJ_PARCELS_FS + "/query", params=params, timeout=60)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as exc:
                logger.warning(f"  fetch attempt {attempt+1} failed: {exc}")
                time.sleep(2 ** attempt)
        else:
            logger.error(f"giving up after 3 retries at offset {offset}")
            return

        features = data.get("features", [])
        if not features:
            return
        for f in features:
            yield f.get("attributes", {})
        if not data.get("exceededTransferLimit"):
            return
        offset += len(features)
        logger.info(f"  fetched {offset} so far...")


def upsert_parcel(db, attrs: dict, source_label: str) -> bool:
    """Upsert one parcel row. Returns True if inserted/updated, False if skipped."""
    block = _pick(attrs, "block")
    lot = _pick(attrs, "lot")
    if not block or not lot:
        return False

    row = dict(
        county_code=str(_pick(attrs, "county_code") or "13"),
        muni_code=str(_pick(attrs, "muni_code") or ""),
        block=str(block),
        lot=str(lot),
        qualifier=str(_pick(attrs, "qualifier") or ""),
        pams_pin=_pick(attrs, "pams_pin"),
        property_location=_pick(attrs, "property_location"),
        property_class=_pick(attrs, "property_class"),
        owner_name=_pick(attrs, "owner_name"),
        owner_street=_pick(attrs, "owner_street"),
        owner_city_state_zip=_pick(attrs, "owner_city_state_zip"),
        land_value=_to_float(_pick(attrs, "land_value")),
        improvement_value=_to_float(_pick(attrs, "improvement_value")),
        total_assessment=_to_float(_pick(attrs, "total_assessment")),
        tax_amount=_to_float(_pick(attrs, "tax_amount")),
        lot_size_acres=_to_float(_pick(attrs, "lot_size_acres")),
        year_built=_to_int(_pick(attrs, "year_built")),
        living_sqft=_to_int(_pick(attrs, "living_sqft")),
        last_sale_date=_to_date(_pick(attrs, "last_sale_date")),
        last_sale_price=_to_float(_pick(attrs, "last_sale_price")),
        last_sale_book=_pick(attrs, "last_sale_book"),
        last_sale_page=_pick(attrs, "last_sale_page"),
        last_sale_nu_code=_pick(attrs, "last_sale_nu_code"),
        data_source=source_label,
        raw_attrs=attrs,
        last_synced_at=datetime.utcnow(),
    )

    stmt = pg_insert(Parcel).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["county_code", "muni_code", "block", "lot", "qualifier"],
        set_={k: v for k, v in row.items() if k not in ("county_code", "muni_code", "block", "lot", "qualifier")},
    )
    db.execute(stmt)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--county", default="13", help="NJ county code (13=Monmouth)")
    p.add_argument("--muni", default="1303", help="NJ muni code (1303=Atlantic Highlands)")
    p.add_argument("--source-label", default=f"NJGIN_MOD-IV_{datetime.utcnow():%Y-%m}",
                   help="String stored in parcels.data_source")
    args = p.parse_args()

    db = SessionLocal()
    n_total = n_upserted = 0
    try:
        for attrs in fetch_features(args.county, args.muni):
            n_total += 1
            if upsert_parcel(db, attrs, args.source_label):
                n_upserted += 1
            if n_total % 500 == 0:
                db.commit()
                logger.info(f"  committed batch ({n_upserted}/{n_total})")
        db.commit()
    finally:
        db.close()

    logger.info(f"Done: {n_upserted}/{n_total} parcels upserted "
                f"(county={args.county}, muni={args.muni})")


if __name__ == "__main__":
    main()
