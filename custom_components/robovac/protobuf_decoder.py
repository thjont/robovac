"""Lightweight protobuf wire-format decoder for extracting values from
protobuf-encoded DPS responses.  No external dependencies — uses only stdlib.

The T2320 (X9 Pro) and similar newer models report a full
``CleanParamResponse`` protobuf (base64-encoded with a 1-byte length prefix)
on the FAN_SPEED DPS instead of a plain string like ``"Quiet"`` or ``"Max"``.
The fan suction value is nested at::

    CleanParamResponse.running_clean_param (field 4)
        → CleanParam.fan (field 6)
            → Fan.suction (field 1)

with enum values QUIET=0, STANDARD=1, TURBO=2, MAX=3, MAX_PLUS=4.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

# Protobuf wire types
_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_LEN = 2
_WIRE_FIXED32 = 5


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a varint from *data* starting at *offset*.

    Returns ``(value, new_offset)``.
    """
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7
    raise ValueError("Truncated varint")


def _skip_field(data: bytes, offset: int, wire_type: int) -> int:
    """Skip over a field value and return the new offset."""
    if wire_type == _WIRE_VARINT:
        _, offset = _read_varint(data, offset)
    elif wire_type == _WIRE_FIXED64:
        offset += 8
    elif wire_type == _WIRE_LEN:
        length, offset = _read_varint(data, offset)
        offset += length
    elif wire_type == _WIRE_FIXED32:
        offset += 4
    else:
        raise ValueError(f"Unknown wire type {wire_type}")
    return offset


def extract_proto_varint(
    data: bytes, field_path: list[int], default: Optional[int] = None
) -> Optional[int]:
    """Navigate nested protobuf messages by *field_path* and return the final
    varint value.

    Each element except the last selects a length-delimited sub-message by
    field number.  The last element selects a varint field whose value is
    returned.

    *default* is returned when all intermediate sub-messages are found but the
    terminal varint field is absent (proto3 omits default-valued fields).

    Returns ``None`` if the path cannot be resolved (missing field, wrong wire
    type, truncated data, etc.).
    """
    view = data
    for depth, target_field in enumerate(field_path):
        is_last = depth == len(field_path) - 1
        offset = 0
        found = False
        while offset < len(view):
            try:
                tag, offset = _read_varint(view, offset)
            except ValueError:
                return None
            field_number = tag >> 3
            wire_type = tag & 0x07

            if field_number == target_field:
                if is_last:
                    if wire_type != _WIRE_VARINT:
                        return None
                    try:
                        value, _ = _read_varint(view, offset)
                    except ValueError:
                        return None
                    return value
                else:
                    if wire_type != _WIRE_LEN:
                        return None
                    length, offset = _read_varint(view, offset)
                    view = view[offset:offset + length]
                    found = True
                    break
            else:
                try:
                    offset = _skip_field(view, offset, wire_type)
                except (ValueError, IndexError):
                    return None
        if not found and not is_last:
            return None
    return default


# Suction enum value → human-readable name
_SUCTION_NAMES: dict[int, str] = {
    0: "Quiet",
    1: "Standard",
    2: "Turbo",
    3: "Max",
    4: "Max Plus",
}


def decode_proto_fan_speed(raw_value: str) -> Optional[str]:
    """Decode a base64-encoded ``CleanParamResponse`` protobuf and return the
    human-readable fan suction name.

    The raw value is expected to be base64 with a 1-byte length prefix before
    the protobuf payload (as observed on T2320 DPS 154).

    Tries ``running_clean_param`` (field 4) first, then falls back to
    ``clean_param`` (field 1).

    Returns ``None`` if decoding fails so the caller can fall through to
    existing logic.
    """
    try:
        data = base64.b64decode(raw_value)
    except Exception:
        return None

    if len(data) < 2:
        return None

    # Strip 1-byte length prefix
    payload = data[1:]

    # Primary: running_clean_param (field 4) → fan (field 6) → suction (field 1)
    # default=0 handles proto3's omission of the Quiet (0) default value
    suction = extract_proto_varint(payload, [4, 6, 1], default=0)
    if suction is None:
        # Fallback: clean_param (field 1) → fan (field 6) → suction (field 1)
        suction = extract_proto_varint(payload, [1, 6, 1], default=0)

    if suction is not None:
        name = _SUCTION_NAMES.get(suction)
        if name is not None:
            return name
        _LOGGER.warning("Unknown fan suction value: %d", suction)

    return None
