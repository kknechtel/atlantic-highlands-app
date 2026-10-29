"""Per-user monthly AI budgets and the deep-thinking permission.

Spend is everything in `llm_usage` attributed to the user since the start
of the current calendar month: chat, deck chat, fact-check, reports. Admins
are uncapped. A budget of 0 means no AI features for that user.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from config import CHAT_DEFAULT_BUDGET_USD

logger = logging.getLogger(__name__)


def effective_budget(user) -> Optional[float]:
    """USD/month cap for `user`, or None when uncapped (admins)."""
    if user.is_admin:
        return None
    if user.chat_budget_usd is not None:
        return float(user.chat_budget_usd)
    return CHAT_DEFAULT_BUDGET_USD


def may_deep_think(user) -> bool:
    return bool(user.is_admin or user.can_deep_think)


def spent_this_month(db: Session, user_id) -> float:
    try:
        return float(db.execute(sql_text(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM llm_usage "
            "WHERE user_id = :uid AND created_at >= date_trunc('month', now())"
        ), {"uid": str(user_id)}).scalar() or 0)
    except Exception as e:  # llm_usage missing on a fresh DB — don't block chat
        logger.warning("spent_this_month failed: %s", e)
        db.rollback()
        return 0.0


def spend_by_user_this_month(db: Session) -> dict[str, float]:
    try:
        rows = db.execute(sql_text(
            "SELECT user_id::text, SUM(estimated_cost_usd) FROM llm_usage "
            "WHERE user_id IS NOT NULL AND created_at >= date_trunc('month', now()) "
            "GROUP BY user_id"
        )).fetchall()
    except Exception as e:
        logger.warning("spend_by_user_this_month failed: %s", e)
        db.rollback()
        return {}
    return {uid: float(total or 0) for uid, total in rows}


def is_over_budget(spent: float, budget: Optional[float]) -> bool:
    return budget is not None and spent >= budget


def enforce_budget(db: Session, user) -> None:
    """Raise 429 if `user` has used up this month's AI budget."""
    budget = effective_budget(user)
    if budget is None:
        return
    if budget <= 0:
        raise HTTPException(status_code=429, detail=(
            "AI chat isn't enabled for your account. Ask the site admin for a signup link."
        ))
    if is_over_budget(spent_this_month(db, user.id), budget):
        raise HTTPException(status_code=429, detail=(
            "You've reached this month's AI chat limit. It resets on the 1st, "
            "or ask the site admin to raise it."
        ))
