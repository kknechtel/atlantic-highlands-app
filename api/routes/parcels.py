"""Parcel routes - search and view Atlantic Highlands property records."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, cast, Float
from sqlalchemy.orm import Session

from database import get_db
from models.parcel import Parcel
from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ParcelListItem(BaseModel):
    id: str
    block: str
    lot: str
    qualifier: str
    property_location: str | None
    property_class: str | None
    owner_name: str | None
    total_assessment: float | None
    tax_amount: float | None
    lot_size_acres: float | None
    year_built: int | None
    last_sale_price: float | None
    last_sale_date: str | None

    class Config:
        from_attributes = True


class ParcelDetail(ParcelListItem):
    pams_pin: str | None
    county_code: str
    muni_code: str
    zoning: str | None
    living_sqft: int | None
    building_class: str | None
    building_description: str | None
    dwelling_units: int | None
    land_description: str | None
    property_use: str | None
    zip5: str | None
    owner_street: str | None
    owner_city_state_zip: str | None
    assessment_year: int | None
    land_value: float | None
    improvement_value: float | None
    exemption_value: float | None
    last_sale_book: str | None
    last_sale_page: str | None
    last_sale_nu_code: str | None
    data_source: str | None


def _to_list_item(p: Parcel) -> ParcelListItem:
    return ParcelListItem(
        id=str(p.id), block=p.block, lot=p.lot, qualifier=p.qualifier or "",
        property_location=p.property_location, property_class=p.property_class,
        owner_name=p.owner_name, total_assessment=p.total_assessment,
        tax_amount=p.tax_amount,
        lot_size_acres=p.lot_size_acres,
        year_built=p.year_built,
        last_sale_price=p.last_sale_price,
        last_sale_date=p.last_sale_date.isoformat() if p.last_sale_date else None,
    )


# Whitelist of sortable columns. Keep this restrictive — the value goes
# straight into ORDER BY, so anything not in this map is a SQL-injection
# vector. The map values are SQLAlchemy expressions (not strings) so
# we can cast block/lot to numeric where useful.
_SORT_COLUMNS = {
    "block_lot": (cast(Parcel.block, Float), cast(Parcel.lot, Float)),
    "property_location": (Parcel.property_location,),
    "property_class": (Parcel.property_class,),
    "owner_name": (Parcel.owner_name,),
    "total_assessment": (Parcel.total_assessment,),
    "tax_amount": (Parcel.tax_amount,),
    "lot_size_acres": (Parcel.lot_size_acres,),
    "year_built": (Parcel.year_built,),
    "last_sale_price": (Parcel.last_sale_price,),
    "last_sale_date": (Parcel.last_sale_date,),
}


@router.get("/", response_model=List[ParcelListItem])
def list_parcels(
    q: Optional[str] = Query(None, description="Search owner_name OR property_location OR block-lot"),
    block: Optional[str] = None,
    property_class: Optional[str] = None,
    min_assessment: Optional[float] = None,
    sort_by: str = Query("block_lot", description=f"One of: {', '.join(_SORT_COLUMNS)}"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    qry = db.query(Parcel)
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(
            Parcel.owner_name.ilike(like),
            Parcel.property_location.ilike(like),
            (Parcel.block + "-" + Parcel.lot).ilike(like),
        ))
    if block:
        qry = qry.filter(Parcel.block == block)
    if property_class:
        qry = qry.filter(Parcel.property_class == property_class)
    if min_assessment is not None:
        qry = qry.filter(Parcel.total_assessment >= min_assessment)

    # Resolve sort columns from the whitelist. Anything unknown silently
    # falls back to the default — keeps the endpoint forgiving while still
    # safe from injection.
    cols = _SORT_COLUMNS.get(sort_by, _SORT_COLUMNS["block_lot"])
    if sort_dir == "desc":
        # Use NULLS LAST so empty year_built / sale_date don't sit at the top
        # on descending sorts (Postgres default puts NULLs first for DESC).
        order_clauses = [c.desc().nullslast() for c in cols]
    else:
        order_clauses = [c.asc().nullslast() for c in cols]

    rows = qry.order_by(*order_clauses).offset(offset).limit(limit).all()
    return [_to_list_item(p) for p in rows]


@router.get("/count")
def count_parcels(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"count": db.query(Parcel).count()}


@router.get("/{parcel_id}", response_model=ParcelDetail)
def get_parcel(
    parcel_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return ParcelDetail(
        **_to_list_item(p).model_dump(),
        pams_pin=p.pams_pin, county_code=p.county_code, muni_code=p.muni_code,
        zoning=p.zoning,
        living_sqft=p.living_sqft,
        building_class=p.building_class,
        building_description=p.building_description,
        dwelling_units=p.dwelling_units,
        land_description=p.land_description,
        property_use=p.property_use,
        zip5=p.zip5,
        owner_street=p.owner_street, owner_city_state_zip=p.owner_city_state_zip,
        assessment_year=p.assessment_year, land_value=p.land_value,
        improvement_value=p.improvement_value, exemption_value=p.exemption_value,
        last_sale_book=p.last_sale_book, last_sale_page=p.last_sale_page,
        last_sale_nu_code=p.last_sale_nu_code, data_source=p.data_source,
    )
