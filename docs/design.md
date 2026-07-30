# Salpinx Design

Salpinx is an annotation-style wrapper around [zenoh](https://zenoh.io/), providing
a concise, Python-idiomatic API for the four core messaging patterns:
publish, subscribe, serve, and request.

## Design Principles

- **Annotation-first**: Decorators declare behavior at definition time, reducing
  imperative boilerplate.
- **Single session**: One global zenoh session per process. No manual session
  management required.
- **Automatic serialization**: MessagePack by default, transparent type conversion
  for dataclasses and built-in types. See [Serialization](serialization.md).
- **Convention over configuration**: Sensible defaults that can be overridden
  when needed.
- **Errors never swallowed**: Every error is either propagated, logged, or
  delivered through an explicit handler callback. No silent failures.

## Session

```python
import salpinx as spx

spx.run()
```

`spx.run()` is the mandatory entry point. It creates a global zenoh session,
registers all previously declared subscribers and services, and blocks until
interrupted (via Ctrl-C or `spx.stop()`).

All salpinx API calls (`spx.publisher`, `@spx.subscribe`, `@spx.serve`,
`spx.put`, `spx.request`, etc.) must be made **before** `spx.run()`. The
session is created at the start of `spx.run()` and destroyed when it returns.

### Session Lifecycle

```python
spx.close()  # immediately tear down the session
spx.stop()   # signal spx.run() to exit gracefully
```

`spx.stop()` sets an internal flag that causes `spx.run()` to exit its
blocking loop. This is useful for programmatic shutdown from another thread.

`spx.close()` immediately tears down the session, releasing all resources.
This is always called as part of the cleanup in `spx.run()`.

## Publishing

### Declared Publisher

```python
temp_pub = spx.publisher("sensor/temp")

temp_pub(25.3)                             # simple value
temp_pub({"celsius": 25.3, "unit": "C"})   # structured data (auto JSON/msgpack)

temp_pub.delete()                          # send a DELETE sample
```

`spx.publisher(key)` returns a callable object. Invoking it publishes data to
the declared key expression. The callable is reusable — call it as many times
as needed.

The `delete()` method sends a zenoh DELETE sample, signalling that the key is
no longer associated with data.

### One-shot Publish

```python
spx.put("sensor/humidity", 60.2)
```

For ad-hoc publishing without a declared publisher. A publisher is created
under the hood and disposed immediately after the put.

## Subscribing

### Decorator Style

```python
@spx.subscribe("sensor/*")
def on_sensor(msg: spx.Message):
    print(f"[{msg.key}] {msg.value}")
```

The decorated function is called whenever data arrives on the matching key
expression. The callback receives a `spx.Message` object:

| Attribute | Description |
|-----------|-------------|
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
salpinx infers the type from the function's type annotation.

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

### Subscriber Error Handling

Exceptions raised inside a subscriber callback are **never silently swallowed**.
By default they are logged at ERROR level to the `salpinx.subscriber` logger.
For custom handling, register a callback:

```python
def on_error(exc: Exception, key: str) -> None:
    print(f"Subscriber on {key} failed: {exc}")

spx.set_error_handler(on_error)
```

The handler receives both the exception and the key expression. Call
`spx.set_error_handler(None)` to restore the default logging behaviour.

## Serving (Queryable)

```python
@spx.serve("math/add")
def add(a: int, b: int) -> int:
    return a + b
```

The decorated function becomes a zenoh queryable. When a query arrives:

1. The query payload is deserialized as a msgpack dict. Each key is matched
   to a function parameter by name.
2. The function is called with those parameters.
3. The return value is serialized (msgpack by default) and sent as a reply.

If the function raises an exception, it is automatically sent as an error
reply, which the requester receives as a `spx.ServiceError`.

### Default Parameters

```python
@spx.serve("nlp/translate")
def translate(text: str, target: str = "en") -> str:
    return f"Translated '{text}' to {target}"
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
zenoh error replies and raised as `spx.ServiceError` on the requester side.
The error reply includes:
- The exception message
- The full Python traceback from the service side
- The key expression and handler function name

The requester receives all of this context in the `spx.ServiceError`:

```python
try:
    spx.request("math/div", a=1, b=0)
except spx.ServiceError as e:
    print(e)                   # [math/div] division by zero (+ remote traceback)
    print(e.service_traceback) # traceback from the service process
    print(e.results)           # [42, 7] — replies collected before the error
    print(e.key_expr)          # math/div
```

Partial results are preserved on a best-effort basis: if multiple replies
arrive and one is an error, previously collected successful replies are
accessible via `e.results`.

## Requesting (Query)

### Single Request

```python
results = spx.request("math/add", a=1, b=2)
# results → [3]
```

Sends a query to the given key expression. Keyword arguments are serialized
as a msgpack dict in the query body. Waits for and returns a list of all
successful replies.

### Error Handling

```python
try:
    results = spx.request("math/div", a=1, b=0)
except spx.ServiceError as e:
    # e carries: .service_traceback, .results, .key_expr
    print(f"Service error: {e}")
```

### Reusable Requester

```python
add = spx.requester("math/add")
results = add(a=1, b=2)
# results → [3]
```

`spx.requester(key)` returns a callable object that can be invoked multiple
times. This avoids re-declaring the querier for every call.

### Timeout

```python
results = spx.request("slow/service", a=1, b=2, timeout=2.0)
```

The `timeout` parameter (in seconds) limits how long the request waits for a
reply.

## Full Example

```python
import salpinx as spx
from dataclasses import dataclass

@dataclass
class Pose:
    x: float
    y: float

temp_pub = spx.publisher("sensor/temp")
pose_pub = spx.publisher("robot/pose")

@spx.subscribe("sensor/temp")
def on_temp(temp: float):
    print(f"Temperature: {temp}C")

@spx.subscribe("robot/pose")
def on_pose(pose: Pose):
    print(f"Robot at ({pose.x}, {pose.y})")

@spx.serve("math/add")
def add(a: int, b: int) -> int:
    return a + b

# Do some work before spin
temp_pub(25.3)
pose_pub(Pose(1.0, 2.0))
results = spx.request("math/add", a=1, b=2)
print(results)

spx.run()
```
