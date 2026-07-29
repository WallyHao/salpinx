"""Request — sending queries and receiving replies."""

from __future__ import annotations

from typing import Any

import msgpack

from salpinx._errors import ServiceError


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

    results: list[Any] = []
    for reply in replies:
        if reply.ok is not None:
            results.append(msgpack.loads(reply.ok.payload.to_bytes()))
        elif reply.err is not None:
            err_data = msgpack.loads(reply.err.payload.to_bytes())
            raise ServiceError(err_data.get("error", "Unknown service error"))

    return results


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

        results: list[Any] = []
        for reply in replies:
            if reply.ok is not None:
                results.append(msgpack.loads(reply.ok.payload.to_bytes()))
            elif reply.err is not None:
                err_data = msgpack.loads(reply.err.payload.to_bytes())
                raise ServiceError(err_data.get("error", "Unknown service error"))

        return results


def requester(key_expr: str, *, timeout: float | None = None) -> Requester:
    return Requester(key_expr, timeout=timeout)
