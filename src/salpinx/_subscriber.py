"""Subscriber — decorator-style subscription with automatic decoding."""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any


class Message:
    """Wraps a received sample with automatic payload decoding."""

    def __init__(self, sample: Any) -> None:
        self._sample = sample

    @property
    def key(self) -> str:
        return str(self._sample.key_expr)

    @property
    def value(self) -> Any:
        from salpinx._serialize import decode

        return decode(self._sample.payload.to_bytes())

    @property
    def timestamp(self) -> Any:
        return self._sample.timestamp


def subscribe(
    key_expr: str,
    *,
    decode: type | Callable[..., Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register a subscriber callback for *key_expr*."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        target_type: type | None = None

        if decode is not None:
            target_type = decode  # type: ignore[assignment]
        else:
            hints = _get_type_hints(fn)
            params = list(inspect.signature(fn).parameters.values())
            if params:
                ann = hints.get(params[0].name)
                if ann is not None:
                    target_type = None if ann is Message else ann

        from salpinx._session import _pending_subscribers, _session

        wrapped = _make_callback(fn, target_type)

        if _session is None:
            _pending_subscribers.append((key_expr, wrapped))
        else:
            _register_subscriber(key_expr, wrapped)

        return fn

    return decorator


def _register_subscriber(key_expr: str, callback: Callable[..., Any]) -> None:
    from salpinx._session import _get_session

    session = _get_session()
    session.declare_subscriber(key_expr, callback)


def _get_type_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        return typing.get_type_hints(fn, include_extras=False)
    except Exception:
        raw: dict[str, Any] = {}
        for name, param in inspect.signature(fn).parameters.items():
            ann = param.annotation
            if ann is not inspect.Parameter.empty:
                raw[name] = ann
        return raw


def _make_callback(
    fn: Callable[..., Any],
    target_type: type | None,
) -> Callable[..., Any]:
    from salpinx._serialize import decode

    def handler(sample: Any) -> Any:
        try:
            msg = Message(sample)
            if target_type is None:
                payload: Any = msg
            else:
                raw = sample.payload.to_bytes()
                payload = decode(raw, target_type)
            return fn(payload)
        except Exception:
            import traceback

            traceback.print_exc()

    return handler
