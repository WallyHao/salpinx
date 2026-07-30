"""Serialization layer using MessagePack with dataclass support."""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any

import msgpack

from salpinx._errors import SerializationError


def encode(value: Any) -> bytes:
    if not isinstance(value, type) and dataclasses.is_dataclass(value):
        value = _dataclass_to_dict(value)
    try:
        data: bytes = msgpack.dumps(value, default=_msgpack_default)
    except TypeError as exc:
        msg = f"Failed to encode value of type {type(value).__name__}"
        raise SerializationError(msg, value_type=type(value)) from exc
    return data


def decode(data: bytes, target_type: type | None = None) -> Any:
    try:
        result: Any = msgpack.loads(data, raw=False)
    except Exception as exc:
        msg = "Failed to decode message payload"
        if target_type is not None:
            msg += f" (target: {target_type.__name__})"
        raise SerializationError(msg, value_type=target_type) from exc

    if target_type is None:
        return result

    if _is_dataclass_type(target_type):
        if isinstance(result, dict):
            try:
                return target_type(**result)
            except TypeError as exc:
                expected = {f.name for f in dataclasses.fields(target_type)}
                received = set(result)
                missing = expected - received
                extra = received - expected
                detail = f"Failed to reconstruct {target_type.__name__}"
                if missing:
                    detail += f"; missing fields: {missing}"
                if extra:
                    detail += f"; unexpected fields: {extra}"
                raise SerializationError(detail, value_type=target_type) from exc
        return result

    return result


def _msgpack_default(obj: Any) -> Any:
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    msg = (
        f"Cannot serialize type {type(obj).__name__}. "
        f"Supported types: None, bool, int, float, str, bytes, list, dict, "
        f"datetime, dataclass."
    )
    raise TypeError(msg)


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if not isinstance(value, type) and dataclasses.is_dataclass(value):
            value = _dataclass_to_dict(value)
        result[field.name] = value
    return result


def _is_dataclass_type(t: type | None) -> bool:
    return t is not None and dataclasses.is_dataclass(t)
