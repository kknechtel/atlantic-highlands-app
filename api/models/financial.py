"""Financial analysis models for town and school financial statements."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class FinancialStatement(Base):
    """A parsed financial statement (budget, audit, CAFR, etc.)."""
    __tablename__ = "financial_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    entity_name = Column(String, nullable=False)  # "Borough of Atlantic Highlands", "Atlantic Highlands School District"
    entity_type = Column(String, nullable=False)  # "town", "school"
    statement_type = Column(String, nullable=False)  # "budget", "audit", "cafr", "annual_report"
    fiscal_year = Column(String, nullable=False)
    fiscal_year_start = Column(DateTime, nullable=True)
    fiscal_year_end = Column(DateTime, nullable=True)

    # Summary figures
    total_revenue = Column(Float, nullable=True)
    total_expenditures = Column(Float, nullable=True)
    surplus_deficit = Column(Float, nullable=True)
    fund_balance = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)

    # Raw extraction data
    raw_extraction = Column(JSONB, default={})
    extraction_model = Column(String, nullable=True)  # which LLM was used
    extraction_confidence = Column(Float, nullable=True)

    status = Column(String, default="pending")  # pending, extracted, verified, error
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    line_items = relationship("FinancialLineItem", back_populates="statement", cascade="all, delete-orphan")


class FinancialLineItem(Base):
    """Individual line items from a financial statement."""
    __tablename__ = "financial_line_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(UUID(as_uuid=True), ForeignKey("financial_statements.id"), nullable=False)
    section = Column(String, nullable=True)  # "Revenue", "Expenditures", "Assets", "Liabilities"
    subsection = Column(String, nullable=True)
    line_name = Column(String, nullable=False)
    amount = Column(Float, nullable=True)
    prior_year_amount = Column(Float, nullable=True)
    budget_amount = Column(Float, nullable=True)
    variance = Column(Float, nullable=True)
    line_order = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONB, default={})

    statement = relationship("FinancialStatement", back_populates="line_items")


class FinancialAnalysis(Base):
    """Stored analysis results comparing financial statements over time."""
    __tablename__ = "financial_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)  # "town", "school"
    analysis_type = Column(String, nullable=False)  # "trend", "comparison", "ratio", "variance"
    fiscal_years = Column(JSONB, default=[])  # list of years included
    statement_ids = Column(JSONB, default=[])  # list of statement IDs analyzed
    results = Column(JSONB, default={})  # structured analysis output
    summary = Column(Text, nullable=True)  # AI-generated narrative summary
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
