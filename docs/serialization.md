# Serialization

Salpinx serializes all messages with [MessagePack](https://msgpack.org/) by
default. MessagePack is a compact binary format that is faster and smaller
than JSON while retaining the same basic type model.

## Built-in Types (Zero Configuration)

The following types are handled by MessagePack natively and require no
additional configuration:

| Python Type | MessagePack Type | Round-trip? |
|---|---|---|
| `None` | nil | Yes |
| `bool` | bool | Yes |
| `int` | integer | Yes |
| `float` | float | Yes |
| `str` | string | Yes |
| `bytes` | binary | Yes |
| `list` | array | Yes |
| `dict` | map | Yes |
| `datetime` | timestamp extension | Yes |

Note: `tuple` is serialized as `list` and deserialized back as `list` (not
`tuple`). This is a MessagePack limitation.

## Dataclass Support (Zero Configuration)

Dataclasses and named tuples are automatically serialized by converting them
to dicts via `dataclasses.fields()` / `getattr()`.

```python
from dataclasses import dataclass

@dataclass
class RobotPose:
    x: float
    y: float
    theta: float

# Publish — dataclass → dict → msgpack
spx.put("robot/pose", RobotPose(1.0, 2.0, 0.5))
```

Nested dataclasses are supported: if a dataclass field is itself a dataclass,
the nested instance is also converted to a dict recursively. However,
deserialization back to the nested dataclass type is not automatic — only the
top-level type annotation on the subscriber callback is used for restoration.

### Type Restoration on Subscribe

When a subscriber callback has a type annotation, salpinx uses it to restore
the target type:

```python
@spx.subscribe("sensor/readings")
def on_readings(data: list):         # deserialized as list
    print(sum(data) / len(data))

@spx.subscribe("robot/pose")
def on_pose(pose: RobotPose):        # deserialized as RobotPose(**data)
    print(pose.x, pose.y)
```

If no type annotation is present, the payload is deserialized as a plain
`dict`.

### Restoration Rules

| Target Type | How data is restored |
|---|---|
| `int` / `float` / `str` / `bytes` / `bool` | Direct passthrough |
| `list` / `dict` | Direct passthrough |
| `datetime` | msgpack timestamp extension → `datetime` |
| `dataclass` | `dict` → `cls(**data)` |
| No annotation | Raw `dict` |

## Encoding and Decoding Options

The `decode` parameter of `@spx.subscribe` can be used to override the
automatic type inference:

```python
# Subscribe with explicit decoding
@spx.subscribe("sensor/temp", decode=int)
def on_temp(temp: float):
    ...
```

When `decode` is specified it takes precedence over the callback's type
annotation.

## Encoded Key Expressions

The serialization format is communicated in the zenoh message's `encoding`
metadata field:

- Default: `application/msgpack`

This allows non-salpinx zenoh clients to inspect the wire format and decode
messages correctly.

## Error Handling

All serialization errors are raised as `spx.SerializationError`, which
includes the problematic type:

```python
try:
    spx.put("sensor/x", some_unknown_object)
except spx.SerializationError as e:
    print(e)             # "Failed to encode data for put() to [sensor/x]: ..."
    print(e.value_type)  # <class '__main__.Custom'>
```

Dataclass reconstruction failures include detailed field mismatch information:

```python
# Missing required fields
# → "Failed to reconstruct Point; missing fields: {'y'}"
# Extra unexpected fields
# → "Failed to reconstruct Point; unexpected fields: {'color'}"
```

The underlying exception (e.g., `TypeError` from messagepack) is always
chained via `__cause__`, preserving the full exception chain for debugging.
