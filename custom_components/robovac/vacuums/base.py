from __future__ import annotations

import base64
import logging
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Protocol, Dict, List, Any, Type, Optional, TYPE_CHECKING

from homeassistant.components.vacuum import VacuumActivity

_LOGGER = logging.getLogger(__name__)

# Setup proto path for protobuf imports
def _setup_proto_path() -> bool:
    """Find and add proto directory to sys.path."""
    # Proto directory is at custom_components/robovac/proto
    proto_path = Path(__file__).parent.parent / "proto"
    if proto_path.exists() and str(proto_path) not in sys.path:
        sys.path.insert(0, str(proto_path))
        return True
    return False

_setup_proto_path()

try:
    import work_status_pb2
    WorkStatus = work_status_pb2.WorkStatus
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    WorkStatus = None  # type: ignore


class CleaningState(StrEnum):
    """High-level cleaning states derived from protobuf WorkStatus."""
    IDLE = "idle"
    SLEEPING = "sleeping"
    CLEANING = "cleaning"
    PAUSED = "paused"
    RETURNING = "returning"
    DOCKED = "docked"
    POSITIONING = "positioning"
    ERROR = "error"
    WASHING_MOP = "washing_mop"
    DRYING_MOP = "drying_mop"


@dataclass
class ParsedStatus:
    """Parsed vacuum status from protobuf WorkStatus message."""
    state: CleaningState
    mode: str | None = None  # auto, room, zone, spot, etc.
    is_scheduled: bool = False
    sub_state: str | None = None  # Additional context like "relocating"
    raw_proto: Any = None  # The parsed protobuf for debugging

    @property
    def display_name(self) -> str:
        """Human-readable status string."""
        if self.sub_state:
            return f"{self.state.value.replace('_', ' ').title()} ({self.sub_state})"
        return self.state.value.replace('_', ' ').title()

    @property
    def activity(self) -> VacuumActivity:
        """Map to Home Assistant VacuumActivity."""
        mapping = {
            CleaningState.IDLE: VacuumActivity.IDLE,
            CleaningState.SLEEPING: VacuumActivity.IDLE,
            CleaningState.CLEANING: VacuumActivity.CLEANING,
            CleaningState.PAUSED: VacuumActivity.PAUSED,
            CleaningState.RETURNING: VacuumActivity.RETURNING,
            CleaningState.DOCKED: VacuumActivity.DOCKED,
            CleaningState.POSITIONING: VacuumActivity.CLEANING,
            CleaningState.ERROR: VacuumActivity.ERROR,
            CleaningState.WASHING_MOP: VacuumActivity.DOCKED,
            CleaningState.DRYING_MOP: VacuumActivity.DOCKED,
        }
        return mapping.get(self.state, VacuumActivity.IDLE)


class RoboVacEntityFeature(IntEnum):
    """Supported features of the RoboVac entity."""

    EDGE = 1
    SMALL_ROOM = 2
    CLEANING_TIME = 4
    CLEANING_AREA = 8
    DO_NOT_DISTURB = 16
    AUTO_RETURN = 32
    CONSUMABLES = 64
    ROOM = 128
    ZONE = 256
    MAP = 512
    BOOST_IQ = 1024


class RobovacCommand(StrEnum):
    START_PAUSE = "start_pause"
    DIRECTION = "direction"
    MODE = "mode"
    STATUS = "status"
    RETURN_HOME = "return_home"
    FAN_SPEED = "fan_speed"
    MOP_LEVEL = "mop_level"
    LOCATE = "locate"
    BATTERY = "battery"
    ERROR = "error"
    CLEANING_AREA = "cleaning_area"
    CLEANING_TIME = "cleaning_time"
    AUTO_RETURN = "auto_return"
    DO_NOT_DISTURB = "do_not_disturb"
    BOOST_IQ = "boost_iq"
    CONSUMABLES = "consumables"


class TuyaCodes(StrEnum):
    """Default DPS codes for Tuya-based vacuums.

    These codes can be overridden in model-specific implementations.
    """
    START_PAUSE = "2"
    DIRECTION = "3"
    MODE = "5"
    STATUS = "15"
    RETURN_HOME = "101"
    FAN_SPEED = "102"
    LOCATE = "103"
    BATTERY_LEVEL = "104"
    ERROR_CODE = "106"
    DO_NOT_DISTURB = "107"
    CLEANING_TIME = "109"
    CLEANING_AREA = "110"
    BOOST_IQ = "118"
    ROOM_CLEAN = "124"
    AUTO_RETURN = "135"


# Default consumables DPS codes
TUYA_CONSUMABLES_CODES = ["142", "116"]


class RobovacModelDetails(Protocol):
    homeassistant_features: int
    robovac_features: int
    commands: Dict[RobovacCommand, Any]
    dps_codes: Dict[str, str] = {}  # Optional model-specific DPS codes
    activity_mapping: Dict[str, VacuumActivity] | None = None
    # Optional patterns for STATUS codes with dynamic content (e.g., timestamps)
    # List of tuples: (prefix, suffix, human_readable_status)
    # Example: [("DA", "FSAA==", "Positioning")] matches any base64 starting with DA, ending with FSAA==
    status_patterns: List[tuple[str, str, str]] | None = None


class ProtobufVacuumModel:
    """Base class for vacuum models that use protobuf for status parsing and command building.

    Subclasses should define:
    - homeassistant_features: Home Assistant vacuum capabilities
    - robovac_features: Custom RoboVac features
    - commands: DPS code mappings
    - Error messages can be customized by overriding ERROR_MESSAGES
    """

    uses_protobuf: bool = True

    # Common error codes from error_code_list_t2080.proto
    ERROR_MESSAGES: Dict[int, str] = {
        1: "Side brush stuck",
        2: "Rolling brush stuck",
        3: "Fan speed abnormal",
        5: "Wheel suspended",
        7: "Collision buffer jammed",
        14: "Low battery shutdown",
        15: "Dustbin not installed",
        18: "Machine tilted",
        19: "Machine trapped",
        139: "Off ground protection",
    }

    @classmethod
    def parse_status(cls, data: str | bytes) -> ParsedStatus:
        """Parse a STATUS value from the device.

        Args:
            data: Base64-encoded protobuf message or raw bytes

        Returns:
            ParsedStatus with decoded state information
        """
        if not PROTOBUF_AVAILABLE:
            _LOGGER.warning("Protobuf not available, returning unknown status")
            return ParsedStatus(state=CleaningState.IDLE)

        original_data = data

        # Decode base64 if string
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
                _LOGGER.debug(
                    "parse_status: decoded base64 %r -> bytes=%s (len=%d)",
                    original_data,
                    data.hex(),
                    len(data)
                )
            except Exception as e:
                _LOGGER.error(f"Failed to decode base64 {original_data!r}: {e}")
                return ParsedStatus(state=CleaningState.IDLE)

        # Skip length prefix byte if present
        if len(data) > 0 and data[0] == len(data) - 1:
            _LOGGER.debug(
                "parse_status: stripped length prefix byte, remaining=%s",
                data[1:].hex()
            )
            data = data[1:]

        # Parse protobuf
        ws = WorkStatus()
        try:
            ws.ParseFromString(data)
            _LOGGER.debug(
                "parse_status: WorkStatus parsed - state=%s, has_mode=%s, has_cleaning=%s, "
                "has_go_home=%s, has_charging=%s, has_relocating=%s, has_go_wash=%s",
                ws.state,
                ws.HasField('mode'),
                ws.HasField('cleaning'),
                ws.HasField('go_home'),
                ws.HasField('charging'),
                ws.HasField('relocating'),
                ws.HasField('go_wash') if hasattr(ws, 'go_wash') else False,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to parse WorkStatus protobuf from {data.hex()}: {e}")
            return ParsedStatus(state=CleaningState.IDLE)

        return cls._interpret_work_status(ws)

    @classmethod
    def _interpret_work_status(cls, ws: Any) -> ParsedStatus:
        """Interpret a parsed WorkStatus message into our status model."""
        _LOGGER.debug(
            "_interpret_work_status: raw state enum value=%d",
            ws.state
        )

        # Check if state value is outside valid enum range (0-8)
        # This indicates an error code is being sent on the status channel
        if ws.state > 8:
            error_code = ws.state
            error_msg = cls._get_error_message(error_code)
            _LOGGER.debug(
                "_interpret_work_status: state > 8, treating as error code %d -> %s",
                error_code,
                error_msg
            )
            return ParsedStatus(
                state=CleaningState.ERROR,
                sub_state=error_msg,
                raw_proto=ws,
            )

        # Determine cleaning mode from ws.mode
        mode = None
        if ws.HasField('mode'):
            mode_map = {
                WorkStatus.Mode.Value.AUTO: "auto",
                WorkStatus.Mode.Value.SELECT_ROOM: "room",
                WorkStatus.Mode.Value.SELECT_ZONE: "zone",
                WorkStatus.Mode.Value.SPOT: "spot",
                WorkStatus.Mode.Value.FAST_MAPPING: "mapping",
            }
            mode = mode_map.get(ws.mode.value, str(ws.mode.value))

        # Check for relocating sub-state
        is_relocating = ws.HasField('relocating')

        # Determine main state based on ws.state and sub-messages
        state = CleaningState.IDLE
        sub_state = None
        is_scheduled = False

        # Map protobuf State enum to our CleaningState
        # First check for relocating - this can happen in multiple states
        if is_relocating:
            state = CleaningState.POSITIONING

        elif ws.state == WorkStatus.State.STANDBY:
            state = CleaningState.IDLE
            # Check if paused
            if ws.HasField('cleaning') and ws.cleaning.state == WorkStatus.Cleaning.RunState.PAUSED:
                state = CleaningState.PAUSED
            elif ws.HasField('go_home') and ws.go_home.state == WorkStatus.GoHome.RunState.PAUSED:
                state = CleaningState.PAUSED
                sub_state = "return paused"

        elif ws.state == WorkStatus.State.SLEEP:
            state = CleaningState.SLEEPING

        elif ws.state == WorkStatus.State.FAULT:
            state = CleaningState.ERROR

        elif ws.state == WorkStatus.State.CHARGING:
            state = CleaningState.DOCKED
            if ws.HasField('charging'):
                if ws.charging.state == WorkStatus.Charging.State.DONE:
                    sub_state = "fully charged"
                elif ws.charging.state == WorkStatus.Charging.State.ABNORMAL:
                    state = CleaningState.ERROR
                    sub_state = "charging error"

        elif ws.state == WorkStatus.State.CLEANING:
            if is_relocating:
                state = CleaningState.POSITIONING
            else:
                state = CleaningState.CLEANING

            # Check cleaning sub-state
            if ws.HasField('cleaning'):
                if ws.cleaning.state == WorkStatus.Cleaning.RunState.PAUSED:
                    state = CleaningState.PAUSED
                is_scheduled = ws.cleaning.scheduled_task

            # Check if going to wash mop
            if ws.HasField('go_wash'):
                if ws.go_wash.mode == WorkStatus.GoWash.Mode.WASHING:
                    state = CleaningState.WASHING_MOP
                elif ws.go_wash.mode == WorkStatus.GoWash.Mode.DRYING:
                    state = CleaningState.DRYING_MOP
                elif ws.go_wash.mode == WorkStatus.GoWash.Mode.NAVIGATION:
                    state = CleaningState.RETURNING
                    sub_state = "to wash station"

        elif ws.state == WorkStatus.State.GO_HOME:
            if is_relocating:
                state = CleaningState.POSITIONING
                sub_state = "finding dock"
            else:
                state = CleaningState.RETURNING

        elif ws.state == WorkStatus.State.REMOTE_CTRL:
            state = CleaningState.CLEANING
            sub_state = "remote control"

        elif ws.state == WorkStatus.State.FAST_MAPPING:
            state = CleaningState.CLEANING
            sub_state = "mapping"

        _LOGGER.debug(
            "_interpret_work_status: final -> state=%s, mode=%s, is_scheduled=%s, "
            "sub_state=%s, is_relocating=%s",
            state.value,
            mode,
            is_scheduled,
            sub_state,
            is_relocating
        )

        return ParsedStatus(
            state=state,
            mode=mode,
            is_scheduled=is_scheduled,
            sub_state=sub_state,
            raw_proto=ws,
        )

    @classmethod
    def parse_error(cls, data: str | bytes) -> str | None:
        """Parse an ERROR value from the device.

        Some devices send status-like protobuf on the error channel.
        This detects that and returns None (no error) in those cases.

        Args:
            data: Base64-encoded value or raw bytes

        Returns:
            Error description string, or None if no error
        """
        _LOGGER.debug("parse_error: input=%r", data)

        if isinstance(data, str):
            # Check if this looks like a WorkStatus message (positioning status)
            if data.startswith("DA") and data.endswith("FSAA=="):
                _LOGGER.debug(
                    "parse_error: detected positioning status pattern (DA...FSAA==), returning None"
                )
                return None

            try:
                raw = base64.b64decode(data)
                _LOGGER.debug("parse_error: decoded base64 -> bytes=%s", raw.hex())
            except Exception as e:
                _LOGGER.debug("parse_error: base64 decode failed: %s, returning as-is", e)
                return data  # Return as-is if can't decode
        else:
            raw = data

        # Try to parse as integer error code
        if len(raw) <= 4:
            try:
                error_code = int.from_bytes(raw, 'little')
                _LOGGER.debug("parse_error: parsed as int error_code=%d", error_code)
                if error_code == 0:
                    _LOGGER.debug("parse_error: error_code=0, returning None (no error)")
                    return None
                error_msg = cls._get_error_message(error_code)
                _LOGGER.debug("parse_error: error_code=%d -> %s", error_code, error_msg)
                return error_msg
            except Exception as e:
                _LOGGER.debug("parse_error: int parsing failed: %s", e)

        # Check if it's a WorkStatus (status sent on error channel)
        if len(raw) > 1 and PROTOBUF_AVAILABLE:
            try:
                ws = WorkStatus()
                test_data = raw[1:] if raw[0] == len(raw) - 1 else raw
                ws.ParseFromString(test_data)
                _LOGGER.debug(
                    "parse_error: parsed as WorkStatus with state=%d",
                    ws.state
                )
                # If it parses as WorkStatus with normal state, it's not an error
                if ws.state in [WorkStatus.State.CLEANING, WorkStatus.State.GO_HOME,
                               WorkStatus.State.STANDBY, WorkStatus.State.CHARGING]:
                    _LOGGER.debug(
                        "parse_error: WorkStatus state=%d is normal, returning None",
                        ws.state
                    )
                    return None
            except Exception as e:
                _LOGGER.debug("parse_error: WorkStatus parsing failed: %s", e)

        result = data.hex() if isinstance(data, bytes) else data
        _LOGGER.debug("parse_error: no match, returning raw: %r", result)
        return result

    @classmethod
    def _get_error_message(cls, code: int) -> str:
        """Get human-readable error message for error code."""
        return cls.ERROR_MESSAGES.get(code, f"Error {code}")
