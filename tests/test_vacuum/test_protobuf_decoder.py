"""Unit tests for the lightweight protobuf wire-format decoder."""

import base64
import pytest

from custom_components.robovac.protobuf_decoder import (
    extract_proto_varint,
    decode_proto_fan_speed,
)


# ---------------------------------------------------------------------------
# Helpers to build protobuf test data
# ---------------------------------------------------------------------------

def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _tag(field: int, wire_type: int) -> bytes:
    return _encode_varint((field << 3) | wire_type)


def _varint_field(field: int, value: int) -> bytes:
    return _tag(field, 0) + _encode_varint(value)


def _len_field(field: int, data: bytes) -> bytes:
    return _tag(field, 2) + _encode_varint(len(data)) + data


def _build_clean_param_response(suction: int) -> str:
    """Build a base64-encoded CleanParamResponse with the given suction value
    and a 1-byte length prefix, matching what the T2320 sends on DPS 154.
    """
    fan = _varint_field(1, suction) if suction > 0 else b""
    clean_type = _len_field(1, _varint_field(1, 2))  # SWEEP_AND_MOP
    mop_mode = _len_field(4, _varint_field(1, 1))  # MIDDLE
    fan_field = _len_field(6, fan)

    running_param = clean_type + mop_mode + fan_field
    clean_param = clean_type + mop_mode + fan_field

    response = _len_field(1, clean_param) + _len_field(4, running_param)
    prefixed = bytes([len(response)]) + response
    return base64.b64encode(prefixed).decode()


# ---------------------------------------------------------------------------
# Tests for extract_proto_varint
# ---------------------------------------------------------------------------

class TestExtractProtoVarint:
    def test_simple_varint(self):
        """Extract a top-level varint field."""
        data = _varint_field(1, 42)
        assert extract_proto_varint(data, [1]) == 42

    def test_nested_varint(self):
        """Extract a varint inside a length-delimited sub-message."""
        inner = _varint_field(3, 99)
        outer = _len_field(2, inner)
        assert extract_proto_varint(outer, [2, 3]) == 99

    def test_deeply_nested(self):
        """Three levels deep (matches CleanParamResponse path)."""
        level3 = _varint_field(1, 7)
        level2 = _len_field(6, level3)
        level1 = _len_field(4, level2)
        assert extract_proto_varint(level1, [4, 6, 1]) == 7

    def test_missing_field_returns_none(self):
        data = _varint_field(1, 10)
        assert extract_proto_varint(data, [5]) is None

    def test_wrong_wire_type_returns_none(self):
        """Requesting a varint on a length-delimited field returns None."""
        data = _len_field(1, b"\x00")
        assert extract_proto_varint(data, [1]) is None

    def test_empty_data_returns_none(self):
        assert extract_proto_varint(b"", [1]) is None

    def test_truncated_data_returns_none(self):
        assert extract_proto_varint(b"\x08", [1]) is None

    def test_skips_unrelated_fields(self):
        """Correctly skips fields that aren't the target."""
        data = _varint_field(1, 10) + _varint_field(2, 20) + _varint_field(3, 30)
        assert extract_proto_varint(data, [3]) == 30

    def test_zero_varint(self):
        """Proto3 default of 0 can still be read when explicitly encoded."""
        data = _varint_field(1, 0)
        assert extract_proto_varint(data, [1]) == 0


# ---------------------------------------------------------------------------
# Tests for decode_proto_fan_speed
# ---------------------------------------------------------------------------

class TestDecodeProtoFanSpeed:
    @pytest.mark.parametrize("suction,expected", [
        (0, "Quiet"),
        (1, "Standard"),
        (2, "Turbo"),
        (3, "Max"),
        (4, "Max Plus"),
    ])
    def test_all_suction_levels(self, suction, expected):
        b64 = _build_clean_param_response(suction)
        assert decode_proto_fan_speed(b64) == expected

    def test_returns_none_for_plain_string(self):
        """A plain fan speed string like 'Quiet' should not be decoded."""
        assert decode_proto_fan_speed("Quiet") is None

    def test_returns_none_for_empty_string(self):
        assert decode_proto_fan_speed("") is None

    def test_returns_none_for_invalid_base64(self):
        assert decode_proto_fan_speed("!!!not-base64!!!") is None

    def test_returns_none_for_too_short_data(self):
        """Single byte after base64 decode is too short."""
        assert decode_proto_fan_speed(base64.b64encode(b"\x05").decode()) is None

    def test_fallback_to_clean_param_field_1(self):
        """When running_clean_param (field 4) is missing, fall back to
        clean_param (field 1).
        """
        fan = _varint_field(1, 2)  # TURBO
        clean_param = _len_field(6, fan)
        # Only field 1 (clean_param), no field 4
        response = _len_field(1, clean_param)
        prefixed = bytes([len(response)]) + response
        b64 = base64.b64encode(prefixed).decode()
        assert decode_proto_fan_speed(b64) == "Turbo"

    def test_prebuilt_max_sample(self):
        """Test with a known pre-built base64 sample for MAX suction."""
        # This sample was generated from the proto structure:
        # CleanParamResponse { clean_param { fan { suction: MAX } },
        #                      running_clean_param { fan { suction: MAX } } }
        sample = "JAoQCgIIAhoCCAEiAggBMgIIAyIQCgIIAhoCCAEiAggBMgIIAw=="
        assert decode_proto_fan_speed(sample) == "Max"
