"""Unit tests for Publisher, Subscriber, Serve, and Request patterns."""

from __future__ import annotations

import unittest.mock
from dataclasses import dataclass

import msgpack
import pytest

import salpinx._session
import salpinx._subscriber
from salpinx._errors import ServiceError
from salpinx._publisher import publisher, put
from salpinx._request import request, requester
from salpinx._serialize import encode
from salpinx._serve import serve
from salpinx._subscriber import Message, subscribe


@dataclass
class _TestPose:
    x: float
    y: float


@pytest.fixture(autouse=True)
def _clean_global_state():
    """Reset global state before each test."""
    salpinx._session._session = None
    salpinx._session._pending_subscribers.clear()
    salpinx._session._pending_services.clear()
    yield
    salpinx._session._session = None
    salpinx._session._pending_subscribers.clear()
    salpinx._session._pending_services.clear()


@pytest.fixture
def mock_session():
    session = unittest.mock.MagicMock()
    salpinx._session._session = session
    return session


def test_publisher_calls_put(mock_session):
    mock_pub = unittest.mock.MagicMock()
    mock_session.declare_publisher.return_value = mock_pub

    pub = publisher("sensor/temp")
    pub(25.3)

    mock_session.declare_publisher.assert_called_once_with("sensor/temp")
    expected_payload = encode(25.3)
    mock_pub.put.assert_called_once()
    actual_payload = mock_pub.put.call_args[0][0]
    assert actual_payload == expected_payload


def test_publisher_reuse_publisher(mock_session):
    mock_pub = unittest.mock.MagicMock()
    mock_session.declare_publisher.return_value = mock_pub

    pub = publisher("sensor/temp")
    pub(10)
    pub(20)

    assert mock_session.declare_publisher.call_count == 1
    assert mock_pub.put.call_count == 2


def test_publisher_delete(mock_session):
    mock_pub = unittest.mock.MagicMock()
    mock_session.declare_publisher.return_value = mock_pub

    pub = publisher("sensor/temp")
    pub.delete()

    mock_pub.delete.assert_called_once()


def test_put_one_shot(mock_session):
    put("sensor/humidity", 60.2)

    mock_session.put.assert_called_once()
    expected_payload = encode(60.2)
    actual_payload = mock_session.put.call_args[0][1]
    assert actual_payload == expected_payload


@pytest.fixture
def mock_zenoh_sample():
    sample = unittest.mock.MagicMock()
    sample.key_expr = "sensor/temp"
    sample.payload.to_bytes.return_value = encode(25.3)
    sample.timestamp = None
    return sample


def test_message_wrapper_value(mock_zenoh_sample):
    msg = Message(mock_zenoh_sample)
    assert msg.value == 25.3


def test_message_wrapper_key(mock_zenoh_sample):
    msg = Message(mock_zenoh_sample)
    assert msg.key == "sensor/temp"


def test_message_wrapper_with_dataclass():
    @dataclass
    class Pose:
        x: float
        y: float

    sample = unittest.mock.MagicMock()
    sample.key_expr = "robot/pose"
    sample.payload.to_bytes.return_value = encode(Pose(1.0, 2.0))
    sample.timestamp = None

    msg = Message(sample)
    assert isinstance(msg.value, dict)
    assert msg.value == {"x": 1.0, "y": 2.0}


class TestSubscriberDecorator:
    def test_registers_pending_before_session(self, _clean_global_state):
        called = []

        @subscribe("sensor/temp")
        def on_temp(temp: float):
            called.append(temp)

        assert len(salpinx._session._pending_subscribers) == 1
        assert salpinx._session._pending_subscribers[0][0] == "sensor/temp"

    def test_registers_directly_when_session_exists(self, mock_session):
        called = []

        @subscribe("sensor/temp")
        def on_temp(temp: float):
            called.append(temp)

        mock_session.declare_subscriber.assert_called_once()
        args = mock_session.declare_subscriber.call_args[0]
        assert args[0] == "sensor/temp"

    def test_callback_receives_message_object(self, mock_session, mock_zenoh_sample):
        received = []

        @subscribe("sensor/temp")
        def on_temp(msg: Message):
            received.append(msg)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert len(received) == 1
        assert isinstance(received[0], Message)
        assert received[0].value == 25.3

    def test_callback_receives_decoded_value(self, mock_session, mock_zenoh_sample):
        received = []

        @subscribe("sensor/temp")
        def on_temp(temp: float):
            received.append(temp)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert len(received) == 1
        assert received[0] == 25.3
        assert isinstance(received[0], float)

    def test_callback_receives_dataclass(self, mock_session):
        sample = unittest.mock.MagicMock()
        sample.key_expr = "robot/pose"
        sample.payload.to_bytes.return_value = encode(_TestPose(1.0, 2.0))
        sample.timestamp = None

        received = []

        @subscribe("robot/pose")
        def on_pose(pose: _TestPose):
            received.append(pose)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(sample)

        assert len(received) == 1
        assert isinstance(received[0], _TestPose)
        assert received[0].x == 1.0
        assert received[0].y == 2.0


class TestServeDecorator:
    def test_registers_pending_before_session(self, _clean_global_state):
        @serve("math/add")
        def add(a: int, b: int) -> int:
            return a + b

        assert len(salpinx._session._pending_services) == 1
        assert salpinx._session._pending_services[0][0] == "math/add"

    def test_registers_queryable_when_session_exists(self, mock_session):
        @serve("math/add")
        def add(a: int, b: int) -> int:
            return a + b

        mock_session.declare_queryable.assert_called_once()

    def test_handler_calls_function_and_replies(self, mock_session):
        @serve("math/add")
        def add(a: int, b: int) -> int:
            return a + b

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"a": 1, "b": 2})

        callback(query)

        expected_reply = msgpack.dumps(3)
        query.reply.assert_called_once_with("math/add", expected_reply)
        query.drop.assert_called_once()

    def test_handler_uses_default_values(self, mock_session):
        @serve("nlp/translate")
        def translate(text: str, target: str = "en") -> str:
            return f"{text}:{target}"

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"text": "hello"})

        callback(query)

        expected_reply = msgpack.dumps("hello:en")
        query.reply.assert_called_once_with("nlp/translate", expected_reply)

    def test_handler_sends_error_on_exception(self, mock_session):
        @serve("math/div")
        def divide(a: float, b: float) -> float:
            if b == 0:
                raise ValueError("division by zero")
            return a / b

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"a": 1, "b": 0})

        callback(query)

        query.reply_err.assert_called_once()
        err_data = msgpack.loads(query.reply_err.call_args[0][0])
        assert "division by zero" in err_data["error"]
        query.drop.assert_called_once()


class TestRequest:
    def test_sends_query_and_returns_replies(self, mock_session):
        reply1 = unittest.mock.MagicMock()
        reply1.ok.payload.to_bytes.return_value = msgpack.dumps(3)
        reply1.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1]
        mock_session.get.return_value = reply_iter

        results = request("math/add", a=1, b=2)
        assert results == [3]

    def test_raises_service_error(self, mock_session):
        reply1 = unittest.mock.MagicMock()
        reply1.ok = None
        reply1.err.payload.to_bytes.return_value = msgpack.dumps(
            {"error": "division by zero"}
        )

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1]
        mock_session.get.return_value = reply_iter

        with pytest.raises(ServiceError, match="division by zero"):
            request("math/div", a=1, b=0)

    def test_requester_calls_querier(self, mock_session):
        mock_querier = unittest.mock.MagicMock()
        mock_session.declare_querier.return_value = mock_querier

        reply1 = unittest.mock.MagicMock()
        reply1.ok.payload.to_bytes.return_value = msgpack.dumps(42)
        reply1.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1]
        mock_querier.get.return_value = reply_iter

        req = requester("math/add")
        results = req(a=3, b=4)
        assert results == [42]

    def test_requester_reuse(self, mock_session):
        mock_querier = unittest.mock.MagicMock()
        mock_session.declare_querier.return_value = mock_querier

        mock_querier.get.return_value = unittest.mock.MagicMock(
            __iter__=lambda s: iter([])
        )

        req = requester("math/add")
        req(a=1, b=2)
        req(a=3, b=4)

        assert mock_session.declare_querier.call_count == 1
        assert mock_querier.get.call_count == 2


class TestServiceError:
    def test_service_error_str(self):
        err = ServiceError("something went wrong")
        assert str(err) == "something went wrong"


class TestMessageProperties:
    def test_message_timestamp_none(self, mock_zenoh_sample):
        msg = Message(mock_zenoh_sample)
        assert msg.timestamp is None
