"""Serve — decorator-style queryable (service) registration."""

from __future__ import annotations

import inspect
import traceback
from collections.abc import Callable
from typing import Any

import msgpack


def serve(key_expr: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register a function as a queryable at *key_expr*."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        from salpinx._session import _pending_services, _session

        if _session is None:
            _pending_services.append((key_expr, fn))
        else:
            _register_service(key_expr, fn)
        return fn

    return decorator


def _register_service(key_expr: str, fn: Callable[..., Any]) -> None:
    from salpinx._session import _get_session

    session = _get_session()
    sig = inspect.signature(fn)

    def handler(query: Any) -> None:
        try:
            raw = query.payload
            if raw is not None:
                body: dict[str, Any] = msgpack.loads(raw.to_bytes())
            else:
                body = {}

            kwargs: dict[str, Any] = {}
            for name, param in sig.parameters.items():
                if name in body:
                    kwargs[name] = body[name]
                elif param.default is not inspect.Parameter.empty:
                    kwargs[name] = param.default

            result = fn(**kwargs)
            reply_payload = msgpack.dumps(result)
            query.reply(key_expr, reply_payload)
        except Exception as exc:
            tb = traceback.format_exc()
            err_payload = msgpack.dumps({"error": str(exc), "traceback": tb})
            query.reply_err(err_payload)
        finally:
            query.drop()

    session.declare_queryable(key_expr, handler)
