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
to dicts via `vars(obj)` / `asdict(obj)`:

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

## Encoding Override

For debugging or interoperability, the encoding can be switched to JSON:

```python
# Publish as JSON
spx.publisher("sensor/temp", encode="json")(25.3)

# Subscribe with explicit JSON decoding
@spx.subscribe("sensor/temp", decode="json")
def on_temp(temp: float):
    ...
```

Available encoding values: `"msgpack"` (default), `"json"`, `"raw"` (bytes
passthrough).

## Encoded Key Expressions

The serialization format is communicated in the zenoh message's `encoding`
metadata field:

- Default: `application/msgpack`
- JSON mode: `application/json`
- Raw mode: `application/octet-stream`

This allows non-salpinx zenoh clients to inspect the wire format and decode
messages correctly.

## Error Handling

If deserialization fails (e.g., the payload is corrupted or the type does not
match), a `spx.DeserializationError` is raised in the subscriber callback
context. It is up to the application to handle or log such errors.
