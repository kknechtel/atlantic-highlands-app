"""
Parcels — Atlantic Highlands property records sourced from NJ MOD-IV.

NJ MOD-IV is the statewide property tax administration data system. Every
parcel has a Block, Lot, and (optionally) Qualifier; the (county-muni-block-lot-qual)
tuple is unique. Atlantic Highlands borough is muni code 1303 in Monmouth County (13).

Data source: NJ DOT/NJGIN publishes a "Parcels and MOD-IV Composite of NJ"
feature service (ArcGIS Online id 533599bbfbaa4748bf39faf1375a8a9c) plus
shapefile downloads per county. Both are public.

This table stores ONE row per parcel (current state). For historical
assessment trends, we'd add a parcel_assessments table keyed by (parcel_id,
year) — see Phase 2 in the plan.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, Date, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base


class Parcel(Base):
    """Current-state parcel record from NJ MOD-IV.

    Block/Lot/Qual together with county+muni form the unique NJ parcel id."""
    __tablename__ = "parcels"
    __table_args__ = (
        UniqueConstraint("county_code", "muni_code", "block", "lot", "qualifier",
                         name="uix_parcel_pid"),
        Index("ix_parcel_owner", "owner_name"),
        Index("ix_parcel_address", "property_location"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    county_code = Column(String, nullable=False)   # "13" = Monmouth
    muni_code = Column(String, nullable=False)     # "1303" = Atlantic Highlands borough
    block = Column(String, nullable=False)
    lot = Column(String, nullable=False)
    qualifier = Column(String, nullable=False, default="")  # "" or "C0001" etc.
    pams_pin = Column(String, nullable=True, index=True)    # NJGIN composite key

    # Location
    property_location = Column(String, nullable=True)
    property_class = Column(String, nullable=True)      # 1=Vacant, 2=Residential, 4A=Commercial, etc.
    property_class_desc = Column(String, nullable=True)
    zoning = Column(String, nullable=True)
    lot_size_acres = Column(Float, nullable=True)
    building_class = Column(String, nullable=True)
    year_built = Column(Integer, nullable=True)
    living_sqft = Column(Integer, nullable=True)

    # Owner
    owner_name = Column(String, nullable=True)
    owner_street = Column(String, nullable=True)
    owner_city_state_zip = Column(String, nullable=True)

    # Assessment (current year)
    assessment_year = Column(Integer, nullable=True)
    land_value = Column(Float, nullable=True)
    improvement_value = Column(Float, nullable=True)
    total_assessment = Column(Float, nullable=True)
    exemption_value = Column(Float, nullable=True)
    tax_amount = Column(Float, nullable=True)
    tax_rate = Column(Float, nullable=True)

    # Last sale
    last_sale_date = Column(Date, nullable=True)
    last_sale_price = Column(Float, nullable=True)
    last_sale_book = Column(String, nullable=True)
    last_sale_page = Column(String, nullable=True)
    last_sale_nu_code = Column(String, nullable=True)   # Non-Usable code; blank = arms-length

    # Provenance
    data_source = Column(String, nullable=True)   # "NJGIN MOD-IV 2024" etc.
    raw_attrs = Column(JSONB, default={})         # full feature attribute bag for any field we didn't parse out
    last_synced_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
