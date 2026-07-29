"""Tests for package metadata."""

from __future__ import annotations

import salpinx


def test_version() -> None:
    """Check the version is a non-empty string."""
    assert isinstance(salpinx.__version__, str)
    assert len(salpinx.__version__) > 0
