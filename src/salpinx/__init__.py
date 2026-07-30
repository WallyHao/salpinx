"""Salpinx — annotation-style zenoh wrapper."""

from __future__ import annotations

from salpinx._errors import SalpinxError, SerializationError, ServiceError
from salpinx._publisher import Publisher, publisher, put
from salpinx._request import Requester, request, requester
from salpinx._serve import serve
from salpinx._session import close, run, stop
from salpinx._subscriber import Message, set_error_handler, subscribe

__version__ = "0.2.0"

__all__ = [
    "Message",
    "Publisher",
    "Requester",
    "SalpinxError",
    "SerializationError",
    "ServiceError",
    "close",
    "publisher",
    "put",
    "request",
    "requester",
    "run",
    "serve",
    "set_error_handler",
    "stop",
    "subscribe",
]
