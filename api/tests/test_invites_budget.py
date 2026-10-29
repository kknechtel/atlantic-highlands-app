"""Signup-link and AI-budget rules. Run from api/: python -m pytest tests"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from services.chat_budget import effective_budget, is_over_budget
from services.invites import consume_invite, grant_raises_budget, invite_is_open

DEFAULT = 5.0


def _invite(**kw):
    base = dict(is_used=False, use_count=0, max_uses=3, chat_budget_usd=10.0, used_by=None,
                expires_at=datetime.utcnow() + timedelta(days=1))
    return SimpleNamespace(**{**base, **kw})


def _user(**kw):
    base = dict(id="u1", is_admin=False, chat_budget_usd=None)
    return SimpleNamespace(**{**base, **kw})


def test_shareable_link_closes_after_max_uses():
    inv = _invite(max_uses=2)
    consume_invite(inv, _user(), new_user=True, default_budget=DEFAULT)
    assert invite_is_open(inv)
    consume_invite(inv, _user(id="u2"), new_user=True, default_budget=DEFAULT)
    assert inv.is_used and not invite_is_open(inv)


def test_legacy_rows_without_counts_are_single_use():
    inv = _invite(max_uses=None, use_count=None)
    assert invite_is_open(inv)
    consume_invite(inv, _user(), new_user=True, default_budget=DEFAULT)
    assert not invite_is_open(inv)


def test_expired_link_is_closed():
    assert not invite_is_open(_invite(expires_at=datetime.utcnow() - timedelta(seconds=1)))


def test_new_user_gets_link_budget_even_if_below_default():
    u = _user(chat_budget_usd=0.0)  # open-signup budget before the link applied
    consume_invite(_invite(chat_budget_usd=2.0), u, new_user=True, default_budget=DEFAULT)
    assert u.chat_budget_usd == 2.0


def test_existing_user_is_never_lowered_by_a_link():
    u = _user(chat_budget_usd=None)  # None = default of 5
    assert not grant_raises_budget(_invite(chat_budget_usd=2.0), u, DEFAULT)
    consume_invite(_invite(chat_budget_usd=2.0), u, new_user=False, default_budget=DEFAULT)
    assert u.chat_budget_usd is None
    consume_invite(_invite(chat_budget_usd=8.0), u, new_user=False, default_budget=DEFAULT)
    assert u.chat_budget_usd == 8.0


def test_budget_enforcement():
    assert effective_budget(_user(is_admin=True, chat_budget_usd=0.0)) is None
    assert effective_budget(_user(chat_budget_usd=0.0)) == 0.0
    assert not is_over_budget(1000.0, None)
    assert is_over_budget(5.0, 5.0) and not is_over_budget(4.99, 5.0)
