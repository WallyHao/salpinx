"""Publisher — reusable callable for publishing data."""

from __future__ import annotations

from typing import Any

from salpinx._errors import SerializationError


class Publisher:
    def __init__(self, key_expr: str) -> None:
        self._key_expr = key_expr
        self._publisher: Any = None

    def _ensure_publisher(self) -> Any:
        if self._publisher is not None:
            return self._publisher
        from salpinx._session import _get_session

        self._publisher = _get_session().declare_publisher(self._key_expr)
        return self._publisher

    def __call__(self, data: Any) -> None:
        from salpinx._serialize import encode

        pub = self._ensure_publisher()
        try:
            payload = encode(data)
        except Exception as exc:
            msg = f"Failed to encode data for publisher [{self._key_expr}]: {exc}"
            raise SerializationError(msg, value_type=type(data)) from exc
        pub.put(payload)

    def delete(self) -> None:
        pub = self._ensure_publisher()
        pub.delete()


def publisher(key_expr: str) -> Publisher:
    return Publisher(key_expr)


def put(key_expr: str, data: Any) -> None:
    from salpinx._serialize import encode
    from salpinx._session import _get_session

    try:
        payload = encode(data)
    except Exception as exc:
        msg = f"Failed to encode data for put() to [{key_expr}]: {exc}"
        raise SerializationError(msg, value_type=type(data)) from exc
    _get_session().put(key_expr, payload)
