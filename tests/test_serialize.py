from __future__ import annotations

import datetime
from dataclasses import dataclass

import msgpack
import pytest

from salpinx._errors import SerializationError
from salpinx._serialize import decode, encode


def test_encode_decode_none():
    data = encode(None)
    assert decode(data) is None


def test_encode_decode_bool():
    data = encode(True)
    assert decode(data) is True

    data = encode(False)
    assert decode(data) is False


def test_encode_decode_int():
    data = encode(42)
    assert decode(data) == 42
    assert isinstance(decode(data), int)


def test_encode_decode_float():
    data = encode(3.14)
    assert decode(data) == pytest.approx(3.14)
    assert isinstance(decode(data), float)


def test_encode_decode_str():
    data = encode("hello")
    assert decode(data) == "hello"
    assert isinstance(decode(data), str)


def test_encode_decode_bytes():
    data = encode(b"\x00\xff\x01")
    assert decode(data) == b"\x00\xff\x01"


def test_encode_decode_list():
    data = encode([1, 2, 3])
    assert decode(data) == [1, 2, 3]


def test_encode_decode_dict():
    data = encode({"a": 1, "b": "x"})
    assert decode(data) == {"a": 1, "b": "x"}


def test_encode_decode_nested():
    data = encode({"data": [1, 2, 3], "name": "test"})
    assert decode(data) == {"data": [1, 2, 3], "name": "test"}


def test_encode_decode_datetime():
    ts = datetime.datetime(2025, 1, 15, 12, 30, 0, tzinfo=datetime.UTC)
    data = encode(ts)
    result = decode(data)
    assert result == "2025-01-15T12:30:00+00:00"


def test_decode_with_type_annotation_int():
    data = encode(42)
    assert decode(data, int) == 42
    assert isinstance(decode(data, int), int)


def test_decode_with_type_annotation_float():
    data = encode(3.14)
    assert decode(data, float) == 3.14


def test_decode_with_type_annotation_str():
    data = encode("world")
    assert decode(data, str) == "world"


@dataclass
class Point:
    x: float
    y: float


@dataclass
class SensorData:
    name: str
    value: float
    unit: str


def test_encode_dataclass():
    p = Point(1.0, 2.0)
    data = encode(p)
    result = msgpack.loads(data)
    assert result == {"x": 1.0, "y": 2.0}


def test_encode_dataclass_with_str_values():
    s = SensorData("temp", 25.3, "C")
    data = encode(s)
    result = msgpack.loads(data)
    assert result == {"name": "temp", "value": 25.3, "unit": "C"}


def test_decode_to_dataclass():
    s = SensorData("temp", 25.3, "C")
    data = encode(s)
    result = decode(data, SensorData)
    assert isinstance(result, SensorData)
    assert result.name == "temp"
    assert result.value == 25.3
    assert result.unit == "C"


def test_decode_to_point():
    p = Point(1.5, 2.5)
    data = encode(p)
    result = decode(data, Point)
    assert isinstance(result, Point)
    assert result.x == 1.5
    assert result.y == 2.5


def test_decode_no_type_annotation_returns_dict():
    s = SensorData("temp", 25.3, "C")
    data = encode(s)
    result = decode(data)
    assert isinstance(result, dict)
    assert result == {"name": "temp", "value": 25.3, "unit": "C"}


def test_encode_unsupported_type_raises():
    class Custom:
        pass

    with pytest.raises(SerializationError, match="Failed to encode"):
        encode(Custom())


def test_decode_dataclass_field_mismatch():
    @dataclass
    class Strict:
        name: str
        value: float

    data = encode({"name": "test"})
    with pytest.raises(SerializationError, match="missing fields"):
        decode(data, Strict)

    data = encode({"name": "test", "value": 1.0, "extra": True})
    with pytest.raises(SerializationError, match="unexpected fields"):
        decode(data, Strict)


def test_decode_error_wraps_msgpack_error():
    with pytest.raises(SerializationError, match="Failed to decode"):
        decode(b"\xff\xfe\xfd", target_type=int)


def test_encode_error_wraps_msgpack_error():
    with pytest.raises(SerializationError, match="Failed to encode"):
        encode(object())


@dataclass
class Outer:
    inner: Point
    label: str


def test_encode_nested_dataclass():
    o = Outer(inner=Point(3.0, 4.0), label="outer")
    data = encode(o)
    result = msgpack.loads(data)
    assert result == {"inner": {"x": 3.0, "y": 4.0}, "label": "outer"}


def test_decode_dataclass_non_dict_fallback():
    @dataclass
    class Dummy:
        x: int

    data = encode(42)
    result = decode(data, Dummy)
    assert result == 42
