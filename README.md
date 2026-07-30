# salpinx

[![PyPI](https://img.shields.io/pypi/v/salpinx)](https://pypi.org/project/salpinx/)
[![Python](https://img.shields.io/pypi/pyversions/salpinx)](https://pypi.org/project/salpinx/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Annotation-style wrapper around [zenoh](https://zenoh.io/) — a zero-configuration,
high-performance pub/sub/query protocol. Salpinx provides a concise, Python-idiomatic
API for publish, subscribe, serve, and request patterns.

## Installation

```bash
pip install salpinx
# or
uv add salpinx
```

Requires Python 3.12+.

## API Overview

Salpinx exposes four primitives through a global module-level API. All
decorators and calls must be made **before** `spx.run()`.

| Operation | API | Description |
|-----------|-----|-------------|
| Publish | `spx.publisher(key)` / `spx.put(key, data)` | Send data on a key expression |
| Subscribe | `@spx.subscribe(key)` | Receive data via a decorated callback |
| Serve | `@spx.serve(key)` | Expose a function as a queryable service |
| Request | `spx.request(key, **kwargs)` / `spx.requester(key)` | Query a service and get replies |
| Lifecycle | `spx.run()` / `spx.stop()` / `spx.close()` | Session management |
| Errors | `spx.set_error_handler(fn)` | Subscriber error callback |

## Publishing

### Declared Publisher

```python
import salpinx as spx

temp_pub = spx.publisher("sensor/temp")

temp_pub(25.3)                              # publish a scalar
temp_pub({"celsius": 25.3, "unit": "C"})    # publish structured data

temp_pub.delete()                           # send a DELETE sample
```

`spx.publisher(key)` returns a callable object. Each call publishes data to
the declared key expression. The callable is reusable — call it as many times
as needed.

### One-shot Publish

```python
spx.put("sensor/humidity", 60.2)
```

For ad-hoc publishing without declaring a publisher. A publisher is created
under the hood and disposed immediately.

## Subscribing

### Decorator Style

```python
@spx.subscribe("sensor/*")
def on_sensor(msg: spx.Message):
    print(f"[{msg.key}] {msg.value}")
```

The decorated function is called whenever data arrives on the matching key
expression. The callback receives a `spx.Message` object with three properties:

| Property | Description |
|----------|-------------|
| `msg.key` | The actual key expression of the received sample |
| `msg.value` | The payload, automatically decoded |
| `msg.timestamp` | Sample timestamp (if available) |

### Typed Decoding

```python
@spx.subscribe("sensor/temp", decode=float)
def on_temp(temp: float):
    if temp > 30:
        print("Overheat alert!")
```

The `decode` parameter controls how the payload is deserialized. If omitted,
salpinx infers the target type from the function's type annotation.

### Dataclass Subscription

```python
from dataclasses import dataclass

@dataclass
class RobotPose:
    x: float
    y: float
    theta: float

@spx.subscribe("robot/pose")
def on_pose(pose: RobotPose):
    print(f"Robot at ({pose.x}, {pose.y})")
```

The payload is automatically deserialized into a `RobotPose` instance using
the type annotation on the callback parameter.

### Wildcard Matching

```python
@spx.subscribe("sensor/**")
def on_any(msg: spx.Message):
    print(f"[{msg.key}] {msg.value}")
```

Key expressions support zenoh wildcards: `*` matches any single segment,
`**` matches zero or more segments.

### Subscriber Error Handling

By default, exceptions raised inside a subscriber callback are logged at
ERROR level to the ``salpinx.subscriber`` logger. To capture errors
programmatically, register a custom handler:

```python
import logging
logging.getLogger("salpinx.subscriber").setLevel(logging.ERROR)

# or use a custom callback
def on_subscriber_error(exc: Exception, key: str) -> None:
    sentry.capture_exception(exc, extra={"key": key})

spx.set_error_handler(on_subscriber_error)
```

The handler receives the exception and the key expression that triggered it.
Pass ``None`` to restore the default logging behaviour.

## Serving (Queryable)

```python
@spx.serve("math/add")
def add(a: int, b: int) -> int:
    return a + b
```

The decorated function becomes a zenoh queryable. When a query arrives:

1. The query payload (msgpack body) is deserialized as a dict.
2. Each dict key is matched to a function parameter by name.
3. The function is called.
4. The return value is serialized and sent back as a reply.

### Default Parameters

```python
@spx.serve("greet")
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"
```

Optional parameters with defaults are supported.

### Error Handling

```python
@spx.serve("math/div")
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b
```

Exceptions raised inside a service function are automatically converted to
zenoh error replies. On the requester side they are raised as
`spx.ServiceError`, which carries the remote traceback and any partially
collected results:

```python
try:
    spx.request("math/div", a=1, b=0)
except spx.ServiceError as e:
    print(e)                   # [math/div] division by zero
    print(e.service_traceback) # remote traceback from the service side
    print(e.results)           # partially successful replies (if any)
    print(e.key_expr)          # the key expression that failed
```

## Requesting (Query)

### Single Request

```python
results = spx.request("math/add", a=1, b=2)
# results → [3]
```

Sends a query to the given key expression. Keyword arguments are serialized
as a msgpack dict in the query body. Returns a list of all successful replies.

### Reusable Requester

```python
add = spx.requester("math/add")
results = add(a=1, b=2)
# results → [3]
```

`spx.requester(key)` returns a callable that can be invoked multiple times.
This avoids re-declaring the querier for each call.

### Error Handling

When a service returns an error, `spx.request()` raises `spx.ServiceError`.
The exception includes the remote traceback for debugging:

```python
try:
    spx.request("math/div", a=1, b=0)
except spx.ServiceError as e:
    print(f"Service error: {e}")
    # e.service_traceback  — remote traceback from the service
    # e.results             — any responses collected before the error
    # e.key_expr            — the key expression queried
```

### Timeout

```python
spx.request("slow/service", a=1, b=2, timeout=2.0)
```

The `timeout` parameter (in seconds) limits how long the request waits for
replies.

## Serialization

Salpinx uses [MessagePack](https://msgpack.org/) for serialization by default.
MessagePack is a compact binary format — faster and smaller than JSON.

### Built-in Types (Zero Configuration)

The following types are handled natively: `None`, `bool`, `int`, `float`,
`str`, `bytes`, `list`, `dict`.

```python
spx.put("sensor/readings", [23.5, 45.1, 18.9])

@spx.subscribe("sensor/readings")
def on_readings(data: list):
    print(sum(data) / len(data))
```

### Dataclass Support

Dataclasses are automatically converted to dicts (via `vars()`), serialized,
and restored on the subscriber side using the type annotation:

```python
@dataclass
class Pose:
    x: float
    y: float

pose_pub = spx.publisher("robot/pose")
pose_pub(Pose(1.0, 2.0))

@spx.subscribe("robot/pose")
def on_pose(pose: Pose):
    print(pose.x, pose.y)
```

No registration or configuration is required.

## Entry Point

```python
spx.run()     # blocks until Ctrl-C or spx.stop()
```

`spx.run()` is the **mandatory** entry point. It creates the global zenoh
session, registers all declared subscribers and services, and blocks until
interrupted. All salpinx API calls must happen **before** `spx.run()`.

For graceful programmatic shutdown, call `spx.stop()` from another thread:

```python
import threading

def shutdown_after(seconds: float) -> None:
    import time
    time.sleep(seconds)
    spx.stop()

threading.Thread(target=shutdown_after, args=(10,), daemon=True).start()
spx.run()
```

`spx.close()` immediately tears down the session without waiting on the run loop.

## Full Example

```python
import logging
import salpinx as spx
from dataclasses import dataclass

# Enable subscriber error logging
logging.getLogger("salpinx.subscriber").setLevel(logging.ERROR)

@dataclass
class Pose:
    x: float
    y: float


# ---- Publishing ----
temp_pub = spx.publisher("sensor/temp")
pose_pub = spx.publisher("robot/pose")

# ---- Subscribing ----
@spx.subscribe("sensor/temp")
def on_temp(temp: float):
    print(f"Temperature: {temp}C")

@spx.subscribe("robot/pose")
def on_pose(pose: Pose):
    print(f"Robot at ({pose.x}, {pose.y})")

# ---- Serving ----
@spx.serve("math/add")
def add(a: int, b: int) -> int:
    return a + b

# ---- Requesting ----
# Do some work before the event loop
temp_pub(25.3)
pose_pub(Pose(1.0, 2.0))

results = spx.request("math/add", a=1, b=2)
print(results)    # → [3]

# ---- Entry Point ----
spx.run()
```

## License

MIT
