"""Request — sending queries and receiving replies."""

from __future__ import annotations

from typing import Any

import msgpack

from salpinx._errors import ServiceError


def _collect_replies(
    replies: Any,
    key_expr: str,
) -> list[Any]:
    results: list[Any] = []
    for reply in replies:
        if reply.ok is not None:
            try:
                results.append(msgpack.loads(reply.ok.payload.to_bytes()))
            except Exception as exc:
                msg = f"Failed to decode successful reply from [{key_expr}]"
                raise ServiceError(msg, results=results, key_expr=key_expr) from exc
        elif reply.err is not None:
            try:
                err_data = msgpack.loads(reply.err.payload.to_bytes())
            except Exception:
                err_data = {"error": "Unknown service error (unable to decode)"}
            raise ServiceError(
                err_data.get("error", "Unknown service error"),
                service_traceback=err_data.get("traceback"),
                results=results,
                key_expr=key_expr,
            )
    return results


def request(
    key_expr: str,
    *,
    timeout: float | None = None,
    **kwargs: Any,
) -> list[Any]:
    """Send a query to *key_expr* and return all successful replies."""
    from salpinx._session import _get_session

    session = _get_session()
    body = msgpack.dumps(kwargs)

    replies = session.get(key_expr, payload=body, timeout=timeout)
    return _collect_replies(replies, key_expr)


class Requester:
    """A reusable query handle bound to a key expression."""

    def __init__(self, key_expr: str, *, timeout: float | None = None) -> None:
        self._key_expr = key_expr
        self._timeout = timeout
        self._querier: Any = None

    def _ensure_querier(self) -> Any:
        if self._querier is not None:
            return self._querier
        from salpinx._session import _get_session

        self._querier = _get_session().declare_querier(
            self._key_expr, timeout=self._timeout
        )
        return self._querier

    def __call__(self, **kwargs: Any) -> list[Any]:
        querier = self._ensure_querier()
        body = msgpack.dumps(kwargs)
        replies = querier.get(payload=body)
        return _collect_replies(replies, self._key_expr)


def requester(key_expr: str, *, timeout: float | None = None) -> Requester:
    return Requester(key_expr, timeout=timeout)
