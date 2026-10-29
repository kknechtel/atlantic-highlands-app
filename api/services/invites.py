"""Invite / signup-link rules, kept free of DB and HTTP so they're testable.

A link with max_uses=1 is the classic single-use invite; a larger max_uses
makes one shareable signup link. Existing rows predate max_uses/use_count,
so None is read as 1/0.
"""
from __future__ import annotations

from datetime import datetime


def invite_is_open(invite, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    if invite.is_used or invite.expires_at < now:
        return False
    return (invite.use_count or 0) < (invite.max_uses or 1)


def grant_raises_budget(invite, user, default_budget: float) -> bool:
    """True if the link's chat budget is more than `user` has now
    (a NULL user budget means the default)."""
    if invite.chat_budget_usd is None:
        return False
    current = user.chat_budget_usd if user.chat_budget_usd is not None else default_budget
    return invite.chat_budget_usd > current


def consume_invite(invite, user, *, new_user: bool, default_budget: float) -> None:
    """Count one use of `invite` by `user` and apply the link's chat budget.

    New users get exactly the link's budget (NULL link budget = default).
    Existing users are only ever raised, never lowered by joining a link."""
    invite.use_count = (invite.use_count or 0) + 1
    invite.used_by = user.id
    invite.is_used = invite.use_count >= (invite.max_uses or 1)
    if new_user:
        user.chat_budget_usd = invite.chat_budget_usd
    elif grant_raises_budget(invite, user, default_budget):
        user.chat_budget_usd = invite.chat_budget_usd
