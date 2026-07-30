"""Unit tests for Publisher, Subscriber, Serve, and Request patterns."""

from __future__ import annotations

import threading
import time
import unittest.mock
from dataclasses import dataclass
from typing import Any

import msgpack
import pytest

import salpinx._session
import salpinx._subscriber
from salpinx._errors import SerializationError, ServiceError
from salpinx._publisher import publisher, put
from salpinx._request import request, requester
from salpinx._serialize import encode
from salpinx._serve import serve
from salpinx._subscriber import (
    Message,
    _get_type_hints,
    set_error_handler,
    subscribe,
)


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
    def test_registers_pending_before_session(self, _clean_global_state) -> None:
        called = []

        @subscribe("sensor/temp")
        def on_temp(temp: float) -> None:
            called.append(temp)

        assert len(salpinx._session._pending_subscribers) == 1
        assert salpinx._session._pending_subscribers[0][0] == "sensor/temp"

    def test_registers_directly_when_session_exists(self, mock_session) -> None:
        called = []

        @subscribe("sensor/temp")
        def on_temp(temp: float) -> None:
            called.append(temp)

        mock_session.declare_subscriber.assert_called_once()
        args = mock_session.declare_subscriber.call_args[0]
        assert args[0] == "sensor/temp"

    def test_callback_receives_message_object(
        self, mock_session, mock_zenoh_sample
    ) -> None:
        received = []

        @subscribe("sensor/temp")
        def on_temp(msg: Message) -> None:
            received.append(msg)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert len(received) == 1
        assert isinstance(received[0], Message)
        assert received[0].value == 25.3

    def test_callback_receives_decoded_value(
        self, mock_session, mock_zenoh_sample
    ) -> None:
        received = []

        @subscribe("sensor/temp")
        def on_temp(temp: float) -> None:
            received.append(temp)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert len(received) == 1
        assert received[0] == 25.3
        assert isinstance(received[0], float)

    def test_callback_receives_dataclass(self, mock_session) -> None:
        sample = unittest.mock.MagicMock()
        sample.key_expr = "robot/pose"
        sample.payload.to_bytes.return_value = encode(_TestPose(1.0, 2.0))
        sample.timestamp = None

        received = []

        @subscribe("robot/pose")
        def on_pose(pose: _TestPose) -> None:
            received.append(pose)

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(sample)

        assert len(received) == 1
        assert isinstance(received[0], _TestPose)
        assert received[0].x == 1.0
        assert received[0].y == 2.0


class TestServeDecorator:
    def test_registers_pending_before_session(self, _clean_global_state) -> None:
        @serve("math/add")
        def add(a: int, b: int) -> int:
            return a + b

        assert len(salpinx._session._pending_services) == 1
        assert salpinx._session._pending_services[0][0] == "math/add"

    def test_registers_queryable_when_session_exists(self, mock_session) -> None:
        @serve("math/add")
        def add(a: int, b: int) -> int:
            return a + b

        mock_session.declare_queryable.assert_called_once()

    def test_handler_calls_function_and_replies(self, mock_session) -> None:
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

    def test_handler_uses_default_values(self, mock_session) -> None:
        @serve("nlp/translate")
        def translate(text: str, target: str = "en") -> str:
            return f"{text}:{target}"

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"text": "hello"})

        callback(query)

        expected_reply = msgpack.dumps("hello:en")
        query.reply.assert_called_once_with("nlp/translate", expected_reply)

    def test_handler_sends_error_on_exception(self, mock_session) -> None:
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
    def test_sends_query_and_returns_replies(self, mock_session) -> None:
        reply1 = unittest.mock.MagicMock()
        reply1.ok.payload.to_bytes.return_value = msgpack.dumps(3)
        reply1.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1]
        mock_session.get.return_value = reply_iter

        results = request("math/add", a=1, b=2)
        assert results == [3]

    def test_raises_service_error(self, mock_session) -> None:
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

    def test_requester_calls_querier(self, mock_session) -> None:
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

    def test_requester_reuse(self, mock_session) -> None:
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
    def test_service_error_str(self) -> None:
        err = ServiceError("something went wrong")
        assert str(err) == "something went wrong"


class TestMessageProperties:
    def test_message_timestamp_none(self, mock_zenoh_sample) -> None:
        msg = Message(mock_zenoh_sample)
        assert msg.timestamp is None


class TestSessionManagement:
    def test_get_session_returns_existing(self, mock_session):
        sess = salpinx._session._get_session()
        assert sess is mock_session

    def test_close_clears_session(self, mock_session):
        assert salpinx._session._session is mock_session
        salpinx._session.close()
        assert salpinx._session._session is None

    def test_flush_pending_subscribers(self, mock_session):
        salpinx._session._session = None

        with unittest.mock.patch(
            "salpinx._session.zenoh.open", return_value=mock_session
        ):

            @subscribe("flush/test")
            def handler(data: int) -> None:
                pass

            assert len(salpinx._session._pending_subscribers) == 1
            salpinx._session._get_session()
            assert salpinx._session._pending_subscribers == []

    def test_flush_pending_services(self, mock_session):
        salpinx._session._session = None

        with unittest.mock.patch(
            "salpinx._session.zenoh.open", return_value=mock_session
        ):

            @serve("flush/svc")
            def svc(a: int) -> int:
                return a

            assert len(salpinx._session._pending_services) == 1
            salpinx._session._get_session()
            assert salpinx._session._pending_services == []

    def test_stop_sets_event(self):
        salpinx._session._stop_event.clear()
        salpinx._session.stop()
        assert salpinx._session._stop_event.is_set()

    def test_run_stops_on_signal(self, mock_session):  # noqa: ARG002
        salpinx._session._stop_event.clear()

        def _stop_after_delay():
            time.sleep(0.1)
            salpinx._session.stop()

        t = threading.Thread(target=_stop_after_delay, daemon=True)
        t.start()
        salpinx._session.run()
        t.join(timeout=1)
        assert salpinx._session._session is None


class TestSubscriberErrorHandler:
    def test_set_error_handler_is_stored(self):
        def dummy_handler(exc: Exception, key: str) -> None:
            pass

        set_error_handler(dummy_handler)
        assert salpinx._subscriber._error_handler is not None
        set_error_handler(None)
        assert salpinx._subscriber._error_handler is None

    def test_callback_error_calls_handler(self, mock_session, mock_zenoh_sample):
        errors: list[Exception] = []

        def handle_error(exc: Exception, key: str) -> None:
            errors.append(exc)

        set_error_handler(handle_error)

        @subscribe("test/error")
        def faulty(data: float) -> None:
            raise ValueError("boom")

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)
        assert str(errors[0]) == "boom"

        set_error_handler(None)

    def test_callback_error_prints_traceback(self, mock_session, mock_zenoh_sample):
        set_error_handler(None)

        @subscribe("test/error2")
        def faulty(data: float) -> None:
            raise RuntimeError("silent")

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

    def test_subscribe_with_explicit_decode(self, mock_session):
        @subscribe("test/explicit", decode=int)
        def handler(val: str) -> None:
            pass

        mock_session.declare_subscriber.assert_called_once()

    def test_subscribe_no_params_callback(self, mock_session):
        @subscribe("test/noparams")
        def handler():
            pass

        mock_session.declare_subscriber.assert_called_once()

    def test_subscribe_invokes_no_param_callback(self, mock_session):
        received = []

        @subscribe("test/noparams")
        def handler(msg: Message) -> None:
            received.append(msg)

        callback = mock_session.declare_subscriber.call_args[0][1]
        sample = unittest.mock.MagicMock()
        sample.key_expr = "test/noparams"
        sample.payload.to_bytes.return_value = encode("ignored")
        sample.timestamp = None
        callback(sample)
        assert len(received) == 1

    def test_get_type_hints_fallback(self):
        # Create a function with an unresolvable annotation to trigger the
        # fallback in _get_type_hints when typing.get_type_hints raises.
        ns: dict[str, Any] = {}
        exec(  # noqa: S102
            "from __future__ import annotations\n"
            "def _fallen(x: NoSuchType, y): pass\n",
            ns,
        )
        func = ns["_fallen"]

        hints = _get_type_hints(func)
        assert isinstance(hints, dict)
        assert hints.get("x") is not None
        assert "y" not in hints


class TestRequestExtended:
    def test_requester_raises_service_error(self, mock_session):
        mock_querier = unittest.mock.MagicMock()
        mock_session.declare_querier.return_value = mock_querier

        reply1 = unittest.mock.MagicMock()
        reply1.ok = None
        reply1.err.payload.to_bytes.return_value = msgpack.dumps(
            {"error": "requester error"}
        )

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1]
        mock_querier.get.return_value = reply_iter

        req = requester("test/svc")
        with pytest.raises(ServiceError, match="requester error"):
            req(arg=1)

    def test_request_skips_empty_reply(self, mock_session):
        reply1 = unittest.mock.MagicMock()
        reply1.ok = None
        reply1.err = None

        reply2 = unittest.mock.MagicMock()
        reply2.ok.payload.to_bytes.return_value = msgpack.dumps(42)
        reply2.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1, reply2]
        mock_session.get.return_value = reply_iter

        results = request("test/svc", arg=1)
        assert results == [42]

    def test_requester_skips_empty_reply(self, mock_session):
        mock_querier = unittest.mock.MagicMock()
        mock_session.declare_querier.return_value = mock_querier

        reply1 = unittest.mock.MagicMock()
        reply1.ok = None
        reply1.err = None

        reply2 = unittest.mock.MagicMock()
        reply2.ok.payload.to_bytes.return_value = msgpack.dumps(99)
        reply2.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply1, reply2]
        mock_querier.get.return_value = reply_iter

        req = requester("test/svc")
        results = req(arg=1)
        assert results == [99]


class TestServeExtended:
    def test_serve_handler_with_none_payload(self, mock_session):
        @serve("test/none")
        def handler() -> str:
            return "no-args"

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload = None

        callback(query)

        expected_reply = msgpack.dumps("no-args")
        query.reply.assert_called_once_with("test/none", expected_reply)
        query.drop.assert_called_once()

    def test_serve_handler_no_matching_params(self, mock_session):
        @serve("test/extra")
        def handler(name: str = "default") -> str:
            return name

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"other": "irrelevant"})

        callback(query)

        expected_reply = msgpack.dumps("default")
        query.reply.assert_called_once_with("test/extra", expected_reply)
        query.drop.assert_called_once()

    def test_serve_handler_missing_required_param(self, mock_session):
        @serve("test/required")
        def handler(name: str) -> str:
            return name

        callback = mock_session.declare_queryable.call_args[0][1]

        query = unittest.mock.MagicMock()
        query.payload.to_bytes.return_value = msgpack.dumps({"other": "irrelevant"})

        callback(query)

        query.reply_err.assert_called_once()
        query.drop.assert_called_once()


class TestServiceErrorExtended:
    def test_with_traceback(self):
        err = ServiceError("boom", service_traceback="Traceback...\n  line 1")
        assert "boom" in str(err)
        assert "Remote traceback:" in str(err)
        assert "Traceback..." in str(err)

    def test_with_partial_results(self):
        err = ServiceError("failed", results=[1, 2, 3])
        assert "Partial results collected: 3" in str(err)

    def test_with_key_expr(self):
        err = ServiceError("oops", key_expr="math/div")
        assert str(err) == "[math/div] oops"

    def test_with_all_fields(self):
        err = ServiceError(
            "failed",
            service_traceback="Traceback...\n  line 5",
            results=[42],
            key_expr="svc/add",
        )
        s = str(err)
        assert "[svc/add] failed" in s
        assert "Remote traceback:" in s
        assert "line 5" in s
        assert "Partial results collected: 1" in s


class TestSerializationErrorDetails:
    def test_value_type_stored(self):
        err = SerializationError("bad", value_type=dict)
        assert err.value_type is dict

    def test_str_contains_message(self):
        err = SerializationError("encode failed")
        assert "encode failed" in str(err)


class TestSubscriberErrorHandlerKey:
    def test_handler_receives_key_expr(self, mock_session, mock_zenoh_sample):
        captured_key: str | None = None

        def handler(exc: Exception, key: str) -> None:
            nonlocal captured_key
            captured_key = key

        set_error_handler(handler)

        @subscribe("my/custom/key")
        def faulty(data: float) -> None:
            raise RuntimeError("x")

        callback = mock_session.declare_subscriber.call_args[0][1]
        callback(mock_zenoh_sample)

        assert captured_key == "my/custom/key"
        set_error_handler(None)


class TestRequestPartialResults:
    def test_service_error_preserves_collected_replies(self, mock_session):
        reply_ok = unittest.mock.MagicMock()
        reply_ok.ok.payload.to_bytes.return_value = msgpack.dumps(1)
        reply_ok.err = None

        reply_err = unittest.mock.MagicMock()
        reply_err.ok = None
        reply_err.err.payload.to_bytes.return_value = msgpack.dumps({"error": "bad"})

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply_ok, reply_err]
        mock_session.get.return_value = reply_iter

        with pytest.raises(ServiceError) as exc_info:
            request("test/partial")
        assert exc_info.value.results == [1]


class TestPublisherEncodeErrors:
    def test_publisher_encode_failure(self, mock_session):
        mock_pub = unittest.mock.MagicMock()
        mock_session.declare_publisher.return_value = mock_pub

        class Unserializable:
            pass

        pub = publisher("sensor/test")
        with pytest.raises(SerializationError, match="sensor/test"):
            pub(Unserializable())

    def test_put_encode_failure(self):
        class Unserializable:
            pass

        with pytest.raises(SerializationError, match=r"put.*sensor/test"):
            put("sensor/test", Unserializable())


class TestRequestDecodeErrors:
    def test_ok_reply_decode_failure(self, mock_session):
        reply = unittest.mock.MagicMock()
        reply.ok.payload.to_bytes.return_value = b"\xff\xfe\xfd"
        reply.err = None

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply]
        mock_session.get.return_value = reply_iter

        with pytest.raises(ServiceError, match="Failed to decode"):
            request("test/bad")

    def test_err_reply_decode_fallback(self, mock_session):
        reply = unittest.mock.MagicMock()
        reply.ok = None
        reply.err.payload.to_bytes.return_value = b"\xff\xfe"

        reply_iter = unittest.mock.MagicMock()
        reply_iter.__iter__.return_value = [reply]
        mock_session.get.return_value = reply_iter

        with pytest.raises(ServiceError, match="Unknown service error"):
            request("test/bad")
