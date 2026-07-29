"""Salpinx — annotation-style zenoh wrapper."""

from __future__ import annotations

from salpinx._errors import ServiceError
from salpinx._publisher import Publisher, publisher, put
from salpinx._request import Requester, request, requester
from salpinx._serve import serve
from salpinx._session import run
from salpinx._subscriber import Message, subscribe

__version__ = "0.1.1"

__all__ = [
    "Message",
    "Publisher",
    "Requester",
    "ServiceError",
    "publisher",
    "put",
    "request",
    "requester",
    "run",
    "serve",
    "subscribe",
]
