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

## Session

```python
import salpinx as spx

spx.run()
```

`spx.run()` initializes a global zenoh session and blocks until interrupted
(typically via Ctrl-C). All decorations (`@spx.subscribe`, `@spx.serve`, etc.)
register against this implicit session.

There is no need to call `spx.init()` — the session is lazily created on
first use and finalized by `spx.run()`.

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

## Serving (Queryable)

```python
@spx.serve("math/add")
def add(a: int, b: int) -> int:
    return a + b
```

The decorated function becomes a zenoh queryable. When a query arrives:

1. Function parameters are extracted from query parameters (e.g.
   `math/add?a=1&b=2` → `a=1, b=2`).
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

### Payload-based Service

```python
@spx.serve("echo")
def echo(body: str) -> str:
    return f"Echo: {body}"
```

If a parameter is named `body`, salpinx maps the query payload (not query
parameters) to it.

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

## Requesting (Query)

### Single Request

```python
result = spx.request("math/add", a=1, b=2)
# result → 3
```

Sends a query to the given key expression with keyword arguments packed as
query parameters. Waits for and returns the first successful reply.

Errors from the service side are raised as `spx.ServiceError`.

### Reusable Requester

```python
add = spx.requester("math/add")
result = add(a=1, b=2)
# result → 3
```

`spx.requester(key)` returns a callable object that can be invoked multiple
times. This avoids re-declaring the querier for every call.

### Timeout

```python
result = spx.request("slow/service", a=1, b=2, timeout=2.0)
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

# Do some work before spinning
temp_pub(25.3)
pose_pub(Pose(1.0, 2.0))
result = spx.request("math/add", a=1, b=2)
print(result)

spx.run()
```
