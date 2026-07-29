"""Error types for salpinx."""

from __future__ import annotations


class ServiceError(Exception):
    """Raised when a service returns an error reply."""
