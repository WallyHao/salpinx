"""Global session management — lazy singleton."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import zenoh

# Global state
_session: zenoh.Session | None = None
_lock = threading.Lock()

# Deferred registrations (before session exists)
_pending_subscribers: list[tuple[str, Callable[..., Any]]] = []
_pending_services: list[tuple[str, Callable[..., Any]]] = []


def _get_session() -> zenoh.Session:
    global _session  # noqa: PLW0603

    sess = _session
    if sess is not None:
        return sess
    with _lock:
        if _session is not None:
            return _session
        _session = zenoh.open(zenoh.Config())
        _flush_pending()
        return _session


def _flush_pending() -> None:
    from salpinx._serve import _register_service
    from salpinx._subscriber import _register_subscriber

    for key, cb in _pending_subscribers:
        _register_subscriber(key, cb)
    _pending_subscribers.clear()

    for key, fn in _pending_services:
        _register_service(key, fn)
    _pending_services.clear()


def run() -> None:
    _get_session()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        close()


def close() -> None:
    global _session  # noqa: PLW0603
    with _lock:
        if _session is not None:
            _session.close()
            _session = None
