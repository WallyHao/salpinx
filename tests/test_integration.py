"""Integration tests using a real zenoh session."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Any

import pytest

import salpinx
import salpinx._session
from salpinx import Message, ServiceError, publisher, put, requester, subscribe

_settle_delay = 0.5


@dataclass
class _Pose:
    x: float
    y: float
    theta: float


@pytest.fixture(autouse=True)
def _session_setup():
    """Ensure a fresh session exists for each integration test."""
    salpinx._session.close()
    salpinx._session._session = None
    salpinx._session._pending_subscribers.clear()
    salpinx._session._pending_services.clear()
    salpinx._session._get_session()
    yield
    salpinx._session.close()
    salpinx._session._session = None
    salpinx._session._pending_subscribers.clear()
    salpinx._session._pending_services.clear()


def _settle():
    """Give zenoh a moment to propagate subscriptions and queryables."""
    time.sleep(0.5)


def test_publish_and_subscribe_basic():
    q: queue.Queue[Any] = queue.Queue()

    @subscribe("salpinx/test/temp")
    def on_temp(temp: float) -> None:
        q.put(temp)

    _settle()

    pub = publisher("salpinx/test/temp")
    pub(25.3)

    result = q.get(timeout=5.0)
    assert result == 25.3


def test_publish_and_subscribe_message_object():
    q: queue.Queue[Message] = queue.Queue()

    @subscribe("salpinx/test/humidity")
    def on_msg(msg: Message) -> None:
        q.put(msg)

    _settle()

    pub = publisher("salpinx/test/humidity")
    pub(60.2)

    msg = q.get(timeout=5.0)
    assert isinstance(msg, Message)
    assert msg.value == 60.2
    assert "salpinx/test/humidity" in msg.key


def test_put_one_shot():
    q: queue.Queue[Any] = queue.Queue()

    @subscribe("salpinx/test/pressure")
    def on_press(val: int) -> None:
        q.put(val)

    _settle()

    put("salpinx/test/pressure", 1013)

    result = q.get(timeout=5.0)
    assert result == 1013


def test_subscribe_with_dataclass():
    q: queue.Queue[_Pose] = queue.Queue()

    @subscribe("salpinx/test/pose")
    def on_pose(pose: _Pose) -> None:
        q.put(pose)

    _settle()

    pub = publisher("salpinx/test/pose")
    pub(_Pose(1.0, 2.0, 0.5))

    result = q.get(timeout=5.0)
    assert isinstance(result, _Pose)
    assert result.x == 1.0
    assert result.y == 2.0
    assert result.theta == 0.5


def test_subscribe_wildcard():
    q: queue.Queue[str] = queue.Queue()

    @subscribe("salpinx/test/*")
    def on_any(msg: Message) -> None:
        q.put(msg.key)

    _settle()

    put("salpinx/test/light", 800)
    put("salpinx/test/sound", 42)

    keys: set[str] = set()
    for _ in range(2):
        try:
            keys.add(q.get(timeout=5.0))
        except queue.Empty:
            break

    assert "salpinx/test/light" in keys
    assert "salpinx/test/sound" in keys


def test_publish_list():
    q: queue.Queue[list[float]] = queue.Queue()

    @subscribe("salpinx/test/readings")
    def on_readings(data: list[float]) -> None:
        q.put(data)

    _settle()

    readings = [23.5, 45.1, 18.9, 30.2]
    put("salpinx/test/readings", readings)

    result = q.get(timeout=5.0)
    assert result == readings


def test_publish_dict():
    q: queue.Queue[dict[str, Any]] = queue.Queue()

    @subscribe("salpinx/test/status")
    def on_status(data: dict[str, Any]) -> None:
        q.put(data)

    _settle()

    status = {"online": True, "uptime": 3600}
    put("salpinx/test/status", status)

    result = q.get(timeout=5.0)
    assert result == status


def test_publish_bytes():
    q: queue.Queue[bytes] = queue.Queue()

    @subscribe("salpinx/test/binary")
    def on_binary(data: bytes) -> None:
        q.put(data)

    _settle()

    binary_data = b"\x00\xff\xab\xcd"
    put("salpinx/test/binary", binary_data)

    result = q.get(timeout=5.0)
    assert result == binary_data


def test_serve_and_request():
    from salpinx import request, serve

    @serve("salpinx/test/math/add")
    def add(a: int, b: int) -> int:
        return a + b

    _settle()

    results = request("salpinx/test/math/add", timeout=5.0, a=3, b=5)
    assert 8 in results


def test_serve_with_default_param():
    from salpinx import request, serve

    @serve("salpinx/test/greet")
    def greet(name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"

    _settle()

    results = request("salpinx/test/greet", timeout=5.0, name="Alice")
    assert "Hello, Alice!" in results

    results = request("salpinx/test/greet", timeout=5.0, name="Bob", greeting="Hi")
    assert "Hi, Bob!" in results


def test_serve_error():
    from salpinx import request, serve

    @serve("salpinx/test/divide")
    def divide(a: float, b: float) -> float:
        if b == 0:
            raise ValueError("division by zero")
        return a / b

    _settle()

    results = request("salpinx/test/divide", timeout=5.0, a=10, b=2)
    assert 5.0 in results

    with pytest.raises(ServiceError, match="division by zero"):
        request("salpinx/test/divide", timeout=5.0, a=1, b=0)


def test_requester():
    from salpinx import serve

    @serve("salpinx/test/multiply")
    def multiply(a: int, b: int) -> int:
        return a * b

    _settle()

    mul = requester("salpinx/test/multiply")
    results = mul(a=6, b=7)
    assert results == [42]

    results = mul(a=3, b=4)
    assert results == [12]


def test_multiple_subscribers_same_key():
    from salpinx import request, serve

    @serve("salpinx/test/echo")
    def echo(msg: str) -> str:
        return f"echo: {msg}"

    _settle()

    results = request("salpinx/test/echo", timeout=5.0, msg="hello")
    assert "echo: hello" in results
