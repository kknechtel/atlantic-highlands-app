"""The settings cache must never make a request wait on a slow refresh."""
import threading
import time

from services import app_settings


def test_stale_cache_is_served_while_another_thread_refreshes(monkeypatch):
    monkeypatch.setattr(app_settings, "_cache", {"CHAT_MODEL": "old"})
    monkeypatch.setattr(app_settings, "_loaded_at", 1.0)  # long stale
    started, release = threading.Event(), threading.Event()

    def slow_load():
        started.set()
        release.wait(5)
        return {"CHAT_MODEL": "new"}

    monkeypatch.setattr(app_settings, "_load", slow_load)
    t = threading.Thread(target=app_settings.saved)
    t.start()
    assert started.wait(2)
    t0 = time.monotonic()
    assert app_settings.saved() == {"CHAT_MODEL": "old"}  # no waiting
    assert time.monotonic() - t0 < 0.5
    release.set()
    t.join(2)
    assert app_settings.saved() == {"CHAT_MODEL": "new"}


def test_failed_refresh_keeps_last_values(monkeypatch):
    monkeypatch.setattr(app_settings, "_cache", {"ANTHROPIC_API_KEY": "k"})
    monkeypatch.setattr(app_settings, "_loaded_at", 1.0)

    def boom():
        raise TimeoutError("pool exhausted")

    monkeypatch.setattr(app_settings, "_load", boom)
    assert app_settings.saved() == {"ANTHROPIC_API_KEY": "k"}
