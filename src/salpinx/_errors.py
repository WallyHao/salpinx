"""Error types for salpinx."""

from __future__ import annotations

from typing import Any


class SalpinxError(Exception):
    """Base exception for all salpinx errors."""


class SerializationError(SalpinxError):
    """Raised when serialization or deserialization fails."""

    def __init__(self, message: str, *, value_type: type | None = None) -> None:
        self.value_type = value_type
        super().__init__(message)


class ServiceError(SalpinxError):
    """Raised when a remote service returns an error reply.

    Attributes:
        service_traceback: The traceback from the remote service, if available.
        results: Any successfully collected replies before the error occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        service_traceback: str | None = None,
        results: list[Any] | None = None,
        key_expr: str | None = None,
    ) -> None:
        self.service_traceback = service_traceback
        self.results = results or []
        self.key_expr = key_expr
        super().__init__(message)

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.key_expr:
            parts[0] = f"[{self.key_expr}] {parts[0]}"
        if self.service_traceback:
            parts.append(f"\nRemote traceback:\n{self.service_traceback}")
        if self.results:
            parts.append(f"\nPartial results collected: {len(self.results)}")
        return "".join(parts)
