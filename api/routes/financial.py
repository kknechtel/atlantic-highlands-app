"""Financial analysis routes - extract, analyze, and compare financial statements."""
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.document import Document
from models.financial import FinancialStatement, FinancialLineItem, FinancialAnalysis
from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class StatementResponse(BaseModel):
    id: str
    document_id: str
    entity_name: str
    entity_type: str
    statement_type: str
    fiscal_year: str
    total_revenue: float | None
    total_expenditures: float | None
    surplus_deficit: float | None
    fund_balance: float | None
    total_debt: float | None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class LineItemResponse(BaseModel):
    id: str
    section: str | None
    subsection: str | None
    line_name: str
    amount: float | None
    prior_year_amount: float | None
    budget_amount: float | None
    variance: float | None

    class Config:
        from_attributes = True


class ExtractRequest(BaseModel):
    document_id: str
    entity_type: str  # "town" or "school"
    statement_type: str  # "budget", "audit", "cafr"


class AnalysisRequest(BaseModel):
    name: str
    entity_type: str
    analysis_type: str  # "trend", "comparison", "ratio", "variance"
    statement_ids: List[str]


class AnalysisResponse(BaseModel):
    id: str
    name: str
    entity_type: str
    analysis_type: str
    fiscal_years: list
    results: dict
    summary: str | None
    created_at: str

    class Config:
        from_attributes = True


@router.get("/statements", response_model=List[StatementResponse])
def list_statements(
    entity_type: Optional[str] = Query(None),
    fiscal_year: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(FinancialStatement)
    if entity_type:
        query = query.filter(FinancialStatement.entity_type == entity_type)
    if fiscal_year:
        query = query.filter(FinancialStatement.fiscal_year == fiscal_year)
    stmts = query.order_by(FinancialStatement.fiscal_year.desc()).all()
    return [
        StatementResponse(
            id=str(s.id),
            document_id=str(s.document_id),
            entity_name=s.entity_name,
            entity_type=s.entity_type,
            statement_type=s.statement_type,
            fiscal_year=s.fiscal_year,
            total_revenue=s.total_revenue,
            total_expenditures=s.total_expenditures,
            surplus_deficit=s.surplus_deficit,
            fund_balance=s.fund_balance,
            total_debt=s.total_debt,
            status=s.status,
            created_at=s.created_at.isoformat(),
        )
        for s in stmts
    ]


@router.get("/statements/{statement_id}", response_model=StatementResponse)
def get_statement(statement_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).first()
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    return StatementResponse(
        id=str(stmt.id),
        document_id=str(stmt.document_id),
        entity_name=stmt.entity_name,
        entity_type=stmt.entity_type,
        statement_type=stmt.statement_type,
        fiscal_year=stmt.fiscal_year,
        total_revenue=stmt.total_revenue,
        total_expenditures=stmt.total_expenditures,
        surplus_deficit=stmt.surplus_deficit,
        fund_balance=stmt.fund_balance,
        total_debt=stmt.total_debt,
        status=stmt.status,
        created_at=stmt.created_at.isoformat(),
    )


@router.get("/statements/{statement_id}/line-items", response_model=List[LineItemResponse])
def get_line_items(statement_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = (
        db.query(FinancialLineItem)
        .filter(FinancialLineItem.statement_id == statement_id)
        .order_by(FinancialLineItem.line_order)
        .all()
    )
    return [
        LineItemResponse(
            id=str(item.id),
            section=item.section,
            subsection=item.subsection,
            line_name=item.line_name,
            amount=item.amount,
            prior_year_amount=item.prior_year_amount,
            budget_amount=item.budget_amount,
            variance=item.variance,
        )
        for item in items
    ]


@router.post("/extract")
async def extract_financial_data(
    req: ExtractRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Extract financial data from an uploaded document using AI."""
    doc = db.query(Document).filter(Document.id == req.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Create a pending statement record
    stmt = FinancialStatement(
        document_id=doc.id,
        entity_name=f"Atlantic Highlands {'Borough' if req.entity_type == 'town' else 'School District'}",
        entity_type=req.entity_type,
        statement_type=req.statement_type,
        fiscal_year=doc.fiscal_year or "Unknown",
        status="processing",
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)

    # Run extraction in background
    from services.financial_extractor import extract_financial_statement
    background_tasks.add_task(extract_financial_statement, str(stmt.id), doc.s3_key)

    return {"statement_id": str(stmt.id), "status": "processing"}


@router.post("/analyze", response_model=AnalysisResponse)
async def create_analysis(
    req: AnalysisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run a financial analysis across selected statements."""
    statements = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.id.in_(req.statement_ids))
        .all()
    )
    if not statements:
        raise HTTPException(status_code=404, detail="No statements found")

    fiscal_years = sorted(set(s.fiscal_year for s in statements))

    from services.financial_analyzer import run_analysis
    results, summary = await run_analysis(req.analysis_type, statements)

    analysis = FinancialAnalysis(
        name=req.name,
        entity_type=req.entity_type,
        analysis_type=req.analysis_type,
        fiscal_years=fiscal_years,
        statement_ids=[str(s.id) for s in statements],
        results=results,
        summary=summary,
        created_by=user.id,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return AnalysisResponse(
        id=str(analysis.id),
        name=analysis.name,
        entity_type=analysis.entity_type,
        analysis_type=analysis.analysis_type,
        fiscal_years=analysis.fiscal_years,
        results=analysis.results,
        summary=analysis.summary,
        created_at=analysis.created_at.isoformat(),
    )


@router.get("/analyses", response_model=List[AnalysisResponse])
def list_analyses(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(FinancialAnalysis)
    if entity_type:
        query = query.filter(FinancialAnalysis.entity_type == entity_type)
    analyses = query.order_by(FinancialAnalysis.created_at.desc()).all()
    return [
        AnalysisResponse(
            id=str(a.id),
            name=a.name,
            entity_type=a.entity_type,
            analysis_type=a.analysis_type,
            fiscal_years=a.fiscal_years,
            results=a.results,
            summary=a.summary,
            created_at=a.created_at.isoformat(),
        )
        for a in analyses
    ]
