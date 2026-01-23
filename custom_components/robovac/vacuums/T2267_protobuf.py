"""RoboVac L60 (T2267) - Protobuf-based implementation prototype.

This is a prototype showing how vacuum models could use protobuf parsing
instead of hardcoded base64 string mappings.
"""
from __future__ import annotations

import base64
import logging
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.components.vacuum import VacuumEntityFeature, VacuumActivity

# Add proto-reference to path for imports
from pathlib import Path

def _setup_proto_path():
    """Find and add proto-reference to sys.path."""
    # Try multiple possible locations
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "proto-reference",  # From vacuums dir
        Path.cwd() / "proto-reference",  # From project root
        Path("/workspaces/robovac/proto-reference"),  # Absolute fallback
    ]
    for p in possible_paths:
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
            return True
    return False

_setup_proto_path()

try:
    import work_status_pb2
    WorkStatus = work_status_pb2.WorkStatus
    PROTOBUF_AVAILABLE = True
except ImportError as e:
    PROTOBUF_AVAILABLE = False
    WorkStatus = None
    _IMPORT_ERROR = str(e)

from .base import RoboVacEntityFeature, RobovacCommand

_LOGGER = logging.getLogger(__name__)


class CleaningState(Enum):
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


class T2267Protobuf:
    """Protobuf-based vacuum model for T2267.

    This class demonstrates how to:
    1. Parse incoming STATUS messages using protobuf
    2. Generate outgoing commands using protobuf
    3. Map protobuf enums to Home Assistant concepts
    """

    # DPS codes for this model
    DPS_MODE = "152"
    DPS_STATUS = "153"
    DPS_DIRECTION = "155"
    DPS_START_PAUSE = "156"
    DPS_DO_NOT_DISTURB = "157"
    DPS_FAN_SPEED = "158"
    DPS_BOOST_IQ = "159"
    DPS_LOCATE = "160"
    DPS_BATTERY = "163"
    DPS_CONSUMABLES = "168"
    DPS_RETURN_HOME = "173"
    DPS_ERROR = "177"

    # Home Assistant features
    homeassistant_features = (
        VacuumEntityFeature.CLEAN_SPOT
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.LOCATE
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.SEND_COMMAND
        | VacuumEntityFeature.START
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.STOP
    )

    robovac_features = (
        RoboVacEntityFeature.DO_NOT_DISTURB
        | RoboVacEntityFeature.BOOST_IQ
    )

    # Fan speed values (these are simple strings, not protobuf)
    FAN_SPEEDS = ["Quiet", "Standard", "Turbo", "Max", "Boost_IQ"]

    def parse_status(self, data: str | bytes) -> ParsedStatus:
        """Parse a STATUS value from the device.

        Args:
            data: Base64-encoded protobuf message or raw bytes

        Returns:
            ParsedStatus with decoded state information
        """
        if not PROTOBUF_AVAILABLE:
            _LOGGER.warning("Protobuf not available, returning unknown status")
            return ParsedStatus(state=CleaningState.IDLE)

        # Decode base64 if string
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
            except Exception as e:
                _LOGGER.error(f"Failed to decode base64: {e}")
                return ParsedStatus(state=CleaningState.IDLE)

        # Skip length prefix byte if present
        if len(data) > 0 and data[0] == len(data) - 1:
            data = data[1:]

        # Parse protobuf
        ws = WorkStatus()
        try:
            ws.ParseFromString(data)
        except Exception as e:
            _LOGGER.error(f"Failed to parse WorkStatus protobuf: {e}")
            return ParsedStatus(state=CleaningState.IDLE)

        return self._interpret_work_status(ws)

    def _interpret_work_status(self, ws: WorkStatus) -> ParsedStatus:
        """Interpret a parsed WorkStatus message into our status model."""
        # Check if state value is outside valid enum range (0-8)
        # This indicates an error code is being sent on the status channel
        if ws.state > 8:
            error_code = ws.state
            return ParsedStatus(
                state=CleaningState.ERROR,
                sub_state=self._get_error_message(error_code),
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

        return ParsedStatus(
            state=state,
            mode=mode,
            is_scheduled=is_scheduled,
            sub_state=sub_state,
            raw_proto=ws,
        )

    def build_command(self, command: str, **kwargs) -> tuple[str, str]:
        """Build a command to send to the device.

        Args:
            command: Command name (start, stop, pause, return_home, spot, etc.)
            **kwargs: Command-specific parameters

        Returns:
            Tuple of (dps_code, base64_encoded_value)
        """
        if not PROTOBUF_AVAILABLE:
            raise RuntimeError("Protobuf not available")

        if command == "start" or command == "auto":
            return self._build_auto_clean_command(**kwargs)
        elif command == "spot":
            return self._build_spot_clean_command(**kwargs)
        elif command == "pause":
            return self._build_pause_command()
        elif command == "resume":
            return self._build_resume_command()
        elif command == "stop":
            return self._build_stop_command()
        elif command == "return_home":
            return self._build_return_home_command()
        elif command == "direction":
            return self._build_direction_command(kwargs.get("direction", "brake"))
        else:
            raise ValueError(f"Unknown command: {command}")

    def _build_auto_clean_command(self, clean_times: int = 1, force_mapping: bool = False) -> tuple[str, str]:
        """Build an auto clean command.

        ModeCtrlRequest with method=START_AUTO_CLEAN(0), auto_clean.clean_times=1
        Protobuf: 08 00 1a 02 08 01 -> with length prefix: 06 08 00 1a 02 08 01
        """
        # Pre-computed: ModeCtrlRequest(method=0, auto_clean={clean_times=1})
        return self.DPS_MODE, "BBoCCAE="

    def _build_spot_clean_command(self, clean_times: int = 1) -> tuple[str, str]:
        """Build a spot clean command.

        ModeCtrlRequest with method=START_SPOT_CLEAN(3), spot_clean.clean_times=1
        """
        # Pre-computed: ModeCtrlRequest(method=3, spot_clean={clean_times=1})
        return self.DPS_MODE, "BggDMgIIAQ=="

    def _build_pause_command(self) -> tuple[str, str]:
        """Build a pause command.

        ModeCtrlRequest with method=PAUSE_TASK(13)
        Protobuf: 08 0d -> with length prefix: 02 08 0d
        """
        return self.DPS_MODE, "AggN"

    def _build_resume_command(self) -> tuple[str, str]:
        """Build a resume command.

        ModeCtrlRequest with method=RESUME_TASK(14)
        """
        return self.DPS_MODE, "AggO"

    def _build_stop_command(self) -> tuple[str, str]:
        """Build a stop command.

        ModeCtrlRequest with method=STOP_TASK(12)
        """
        return self.DPS_MODE, "AggM"

    def _build_return_home_command(self) -> tuple[str, str]:
        """Build a return home command.

        ModeCtrlRequest with method=START_GOHOME(6)
        """
        return self.DPS_MODE, "AggG"

    def _build_direction_command(self, direction: str) -> tuple[str, str]:
        """Build a remote control direction command.

        RemoteCtrl message with direction enum.
        """
        # Pre-computed direction commands
        direction_commands = {
            "brake": "AggA",     # direction=BRAKE(0)
            "forward": "AggB",   # direction=FORWARD(1)
            "back": "AggC",      # direction=BACK(2)
            "left": "AggD",      # direction=LEFT(3)
            "right": "AggE",     # direction=RIGHT(4)
        }
        return self.DPS_DIRECTION, direction_commands.get(direction.lower(), "AggA")

    def _encode_with_length_prefix(self, data: bytes) -> str:
        """Encode protobuf data with length prefix as base64."""
        # Prepend length byte
        prefixed = bytes([len(data)]) + data
        return base64.b64encode(prefixed).decode('ascii')

    def parse_error(self, data: str | bytes) -> str | None:
        """Parse an ERROR value from the device.

        Some devices send status-like protobuf on the error channel.
        This detects that and returns None (no error) in those cases.

        Args:
            data: Base64-encoded value or raw bytes

        Returns:
            Error description string, or None if no error
        """
        if isinstance(data, str):
            # Check if this looks like a WorkStatus message (starts with certain prefixes)
            if data.startswith("DA") and data.endswith("FSAA=="):
                # This is a positioning status, not an error
                return None

            try:
                raw = base64.b64decode(data)
            except Exception:
                return data  # Return as-is if can't decode
        else:
            raw = data

        # Try to parse as integer error code
        if len(raw) <= 4:
            try:
                error_code = int.from_bytes(raw, 'little')
                if error_code == 0:
                    return None
                return self._get_error_message(error_code)
            except Exception:
                pass

        # Check if it's a WorkStatus (status sent on error channel)
        if len(raw) > 1 and PROTOBUF_AVAILABLE:
            try:
                ws = WorkStatus()
                test_data = raw[1:] if raw[0] == len(raw) - 1 else raw
                ws.ParseFromString(test_data)
                # If it parses as WorkStatus, it's not an error
                if ws.state in [WorkStatus.State.CLEANING, WorkStatus.State.GO_HOME,
                               WorkStatus.State.STANDBY, WorkStatus.State.CHARGING]:
                    return None
            except Exception:
                pass

        return data.hex() if isinstance(data, bytes) else data

    def _get_error_message(self, code: int) -> str:
        """Get human-readable error message for error code."""
        # Common error codes from error_code_list_t2080.proto
        error_messages = {
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
        return error_messages.get(code, f"Error {code}")


# Demo/test code
if __name__ == "__main__":
    model = T2267Protobuf()

    # Test parsing some known status values
    test_values = [
        ("BgoAEAUyAA==", "Cleaning"),
        ("BgoAEAVSAA==", "Positioning"),
        ("CAoAEAUyAggB", "Paused"),
        ("BBADGgA=", "Charging"),
        ("AA==", "Standby"),
        ("DAi65cqGwqLyzgFSAA==", "Positioning with timestamp"),
    ]

    print("=== Status Parsing Tests ===")
    for b64_value, expected in test_values:
        result = model.parse_status(b64_value)
        print(f"\n{b64_value}:")
        print(f"  Expected: {expected}")
        print(f"  Got: {result.display_name}")
        print(f"  Activity: {result.activity}")
        if result.raw_proto:
            print(f"  Proto state: {result.raw_proto.state}")

    if PROTOBUF_AVAILABLE:
        print("\n=== Command Building Tests ===")
        commands = ["start", "spot", "pause", "stop", "return_home"]
        for cmd in commands:
            dps, value = model.build_command(cmd)
            print(f"{cmd}: DPS={dps}, value={value}")
