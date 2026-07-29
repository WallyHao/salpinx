"""Publisher — reusable callable for publishing data."""

from __future__ import annotations

from typing import Any


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
        payload = encode(data)
        pub.put(payload)

    def delete(self) -> None:
        pub = self._ensure_publisher()
        pub.delete()


def publisher(key_expr: str) -> Publisher:
    return Publisher(key_expr)


def put(key_expr: str, data: Any) -> None:
    from salpinx._serialize import encode
    from salpinx._session import _get_session

    payload = encode(data)
    _get_session().put(key_expr, payload)
