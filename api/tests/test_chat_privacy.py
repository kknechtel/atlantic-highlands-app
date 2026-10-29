"""Chats belong to the person who had them — no admin exception."""
from types import SimpleNamespace

from routes.chat import _session_access


class _DB:
    def __init__(self, owners):
        self.owners = owners

    def execute(self, *_a, **_k):
        return SimpleNamespace(fetchall=lambda: [(o,) for o in self.owners])


def test_session_access():
    me = SimpleNamespace(id="u1", is_admin=True)
    assert _session_access(_DB([]), "s", me) == "new"
    assert _session_access(_DB(["u1"]), "s", me) == "mine"
    assert _session_access(_DB(["u2"]), "s", me) == "other"      # admin gets no exception
    assert _session_access(_DB([None]), "s", me) == "other"      # unowned legacy rows
    assert _session_access(_DB(["u1", "u2"]), "s", me) == "other"
