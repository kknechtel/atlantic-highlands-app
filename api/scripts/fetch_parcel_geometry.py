#!/usr/bin/env python3
"""
Pull parcel polygons from the same NJGIN feature service the attribute
ingester uses, but with `returnGeometry=true`. Stores GeoJSON
Polygon/MultiPolygon in parcels.geometry and a {lng,lat} centroid in
parcels.centroid for cheap point queries (and Leaflet marker placement).

The ArcGIS REST API returns geometry in the service's native spatial
reference; we request EPSG:4326 (WGS84 lat/lon) via outSR so the values
go straight into a Leaflet map without re-projection.

Idempotent — re-running overwrites geometry but leaves attributes alone.

Usage:
    DATABASE_URL=... python -m scripts.fetch_parcel_geometry
"""
import argparse
import logging
import os
import sys
import time
from typing import Iterator

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.parcel import Parcel

logger = logging.getLogger("fetch_parcel_geometry")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

NJ_PARCELS_FS = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu"
    "/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0"
)


def _esri_to_geojson(esri_geom: dict) -> dict | None:
    """ArcGIS REST API returns polygons as `{"rings": [[[x,y],...]]}`.
    Convert to GeoJSON. A multi-ring polygon = outer ring + holes (per
    ArcGIS docs, outer rings are clockwise, holes are counter-clockwise).
    We don't bother detecting hole orientation here — Leaflet renders the
    first ring as the polygon and the rest as holes regardless.
    """
    if not esri_geom or "rings" not in esri_geom:
        return None
    rings = esri_geom["rings"]
    if not rings:
        return None
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    # Multiple rings — treat as a single polygon with holes. The composite
    # rarely has multi-polygons (one parcel can span multiple boundaries
    # but it's unusual for AH); if needed we'd detect ring nesting here.
    return {"type": "Polygon", "coordinates": rings}


def _bbox_centroid(geom: dict) -> dict | None:
    """Quick centroid via bounding-box center. Good enough for label
    placement; for true area-weighted centroid we'd use shapely."""
    if not geom or "coordinates" not in geom:
        return None
    xs, ys = [], []
    def walk(coords):
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for c in coords:
                walk(c)
    walk(geom["coordinates"])
    if not xs or not ys:
        return None
    return {"type": "Point", "coordinates": [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]}


def fetch_features(county: str, muni_name: str, page_size: int = 1000) -> Iterator[dict]:
    where = f"MUN_NAME='{muni_name}'"
    if county:
        where = f"COUNTY='{county}' AND " + where
    offset = 0
    sess = requests.Session()
    sess.headers["User-Agent"] = "ah-app/parcels-geom-ingest"

    while True:
        params = {
            "where": where,
            # PCL_GUID + the natural-key fields so we can match server-side
            "outFields": "PCL_GUID,PCLBLOCK,PCLLOT,PCLQCODE,PAMS_PIN",
            "returnGeometry": "true",
            "outSR": 4326,
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
            yield f
        if not data.get("exceededTransferLimit"):
            return
        offset += len(features)
        logger.info(f"  fetched {offset} so far...")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--county", default="MONMOUTH")
    p.add_argument("--muni-name", default="ATLANTIC HIGHLANDS BORO")
    args = p.parse_args()

    db = SessionLocal()
    matched = updated = no_match = 0
    try:
        for feature in fetch_features(args.county, args.muni_name):
            attrs = feature.get("attributes") or {}
            geom = feature.get("geometry") or {}
            block = attrs.get("PCLBLOCK")
            lot = attrs.get("PCLLOT")
            if not block or not lot:
                continue

            geojson = _esri_to_geojson(geom)
            centroid = _bbox_centroid(geojson) if geojson else None

            # Match by (block, lot, qualifier) — same uniqueness our existing
            # rows use. PAMS_PIN would be cleaner but we already key on the
            # block/lot tuple in the attribute ingester.
            q = (
                db.query(Parcel)
                .filter(Parcel.block == str(block))
                .filter(Parcel.lot == str(lot))
                .filter(Parcel.qualifier == (str(attrs.get("PCLQCODE") or "")))
            )
            parcel = q.first()
            if not parcel:
                no_match += 1
                continue

            matched += 1
            if geojson:
                parcel.geometry = geojson
                parcel.centroid = centroid
                updated += 1

            if matched % 500 == 0:
                db.commit()
                logger.info(f"  committed batch — matched={matched} updated={updated}")
        db.commit()
    finally:
        db.close()

    logger.info(
        f"Done: matched={matched} updated={updated} no_match={no_match}"
    )


if __name__ == "__main__":
    main()
