"""Serialization layer using MessagePack with dataclass support."""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any

import msgpack


def encode(value: Any) -> bytes:
    if not isinstance(value, type) and dataclasses.is_dataclass(value):
        value = _dataclass_to_dict(value)
    data: bytes = msgpack.dumps(value, default=_msgpack_default)
    return data


def decode(data: bytes, target_type: type | None = None) -> Any:
    result: Any = msgpack.loads(data, raw=False)

    if target_type is None:
        return result

    if _is_dataclass_type(target_type):
        if isinstance(result, dict):
            return target_type(**result)
        return result

    return result


def _msgpack_default(obj: Any) -> Any:
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    msg = f"Cannot serialize type {type(obj)}"
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
