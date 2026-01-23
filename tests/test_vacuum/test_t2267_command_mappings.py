"""Tests for T2267 command mappings and DPS codes."""

import pytest
from unittest.mock import patch

from homeassistant.components.vacuum import VacuumActivity

from custom_components.robovac.robovac import RoboVac
from custom_components.robovac.vacuums.base import RobovacCommand, CleaningState


@pytest.fixture
def mock_t2267_robovac() -> RoboVac:
    """Create a mock T2267 RoboVac instance for testing."""
    with patch("custom_components.robovac.robovac.TuyaDevice.__init__", return_value=None):
        robovac = RoboVac(
            model_code="T2267",
            device_id="test_id",
            host="192.168.1.100",
            local_key="test_key",
        )
        return robovac


def test_t2267_dps_codes(mock_t2267_robovac: RoboVac) -> None:
    """Test that T2267 has the correct DPS codes."""
    dps_codes = mock_t2267_robovac.getDpsCodes()

    assert dps_codes["MODE"] == "152"
    assert dps_codes["STATUS"] == "153"
    assert dps_codes["DIRECTION"] == "155"
    assert dps_codes["START_PAUSE"] == "156"
    assert dps_codes["DO_NOT_DISTURB"] == "157"
    assert dps_codes["FAN_SPEED"] == "158"
    assert dps_codes["BOOST_IQ"] == "159"
    assert dps_codes["LOCATE"] == "160"
    assert dps_codes["BATTERY_LEVEL"] == "163"
    assert dps_codes["CONSUMABLES"] == "168"
    assert dps_codes["RETURN_HOME"] == "173"
    assert dps_codes["ERROR_CODE"] == "177"


def test_t2267_mode_command_values(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 MODE command value mappings (protobuf-based)."""
    # These are protobuf-encoded commands
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "auto") == "BBoCCAE="
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "pause") == "AggN"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "spot") == "BggDMgIIAQ=="
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "return") == "AggG"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "resume") == "AggO"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "stop") == "AggM"

    # Unknown returns as-is
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.MODE, "unknown") == "unknown"


def test_t2267_fan_speed_command_values(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 FAN_SPEED command value mappings."""
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "quiet") == "Quiet"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "standard") == "Standard"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "turbo") == "Turbo"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "max") == "Max"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "boost_iq") == "Boost_IQ"

    # Unknown returns as-is
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.FAN_SPEED, "unknown") == "unknown"


def test_t2267_direction_command_values(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 DIRECTION command value mappings (protobuf-based)."""
    # These are protobuf-encoded direction commands
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "brake") == "AggA"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "forward") == "AggB"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "back") == "AggC"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "left") == "AggD"
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "right") == "AggE"

    # Unknown returns as-is
    assert mock_t2267_robovac.getRoboVacCommandValue(RobovacCommand.DIRECTION, "unknown") == "unknown"


def test_t2267_command_codes(mock_t2267_robovac: RoboVac) -> None:
    """Test that T2267 command codes are correctly defined on model."""
    commands = mock_t2267_robovac.model_details.commands

    assert commands[RobovacCommand.MODE]["code"] == 152
    assert commands[RobovacCommand.STATUS]["code"] == 153
    assert commands[RobovacCommand.DIRECTION]["code"] == 155
    assert commands[RobovacCommand.START_PAUSE]["code"] == 156
    assert commands[RobovacCommand.DO_NOT_DISTURB]["code"] == 157
    assert commands[RobovacCommand.FAN_SPEED]["code"] == 158
    assert commands[RobovacCommand.BOOST_IQ]["code"] == 159
    assert commands[RobovacCommand.LOCATE]["code"] == 160
    assert commands[RobovacCommand.BATTERY]["code"] == 163
    assert commands[RobovacCommand.CONSUMABLES]["code"] == 168
    assert commands[RobovacCommand.RETURN_HOME]["code"] == 173
    assert commands[RobovacCommand.ERROR]["code"] == 177


def test_t2267_protobuf_status_parsing(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 protobuf-based STATUS parsing."""
    # Verify this model uses protobuf
    assert mock_t2267_robovac.uses_protobuf()

    # Test parsing various status codes
    test_cases = [
        # (base64_status, expected_state, expected_display_contains)
        ("BgoAEAUyAA==", CleaningState.CLEANING, "Cleaning"),
        ("BgoAEAVSAA==", CleaningState.POSITIONING, "Positioning"),
        ("CAoAEAUyAggB", CleaningState.PAUSED, "Paused"),
        ("BBADGgA=", CleaningState.DOCKED, "Docked"),
        ("BhADGgIIAQ==", CleaningState.DOCKED, "Docked"),  # Fully charged
        ("BBAHQgA=", CleaningState.RETURNING, "Returning"),
        ("AA==", CleaningState.IDLE, "Idle"),
        ("AhAB", CleaningState.SLEEPING, "Sleeping"),
    ]

    for base64_status, expected_state, expected_display in test_cases:
        parsed = mock_t2267_robovac.parse_protobuf_status(base64_status)
        assert parsed is not None, f"Failed to parse {base64_status}"
        assert parsed.state == expected_state, f"Expected {expected_state} for {base64_status}, got {parsed.state}"
        assert expected_display in parsed.display_name, f"Expected '{expected_display}' in {parsed.display_name}"


def test_t2267_protobuf_status_activity(mock_t2267_robovac: RoboVac) -> None:
    """Test that protobuf-parsed status maps correctly to VacuumActivity."""
    test_cases = [
        ("BgoAEAUyAA==", VacuumActivity.CLEANING),  # Cleaning
        ("BgoAEAVSAA==", VacuumActivity.CLEANING),  # Positioning -> CLEANING
        ("CAoAEAUyAggB", VacuumActivity.PAUSED),    # Paused
        ("BBADGgA=", VacuumActivity.DOCKED),        # Charging
        ("BBAHQgA=", VacuumActivity.RETURNING),     # Going home
        ("AA==", VacuumActivity.IDLE),              # Standby
        ("AhAB", VacuumActivity.IDLE),              # Sleeping -> IDLE
    ]

    for base64_status, expected_activity in test_cases:
        parsed = mock_t2267_robovac.parse_protobuf_status(base64_status)
        assert parsed is not None
        assert parsed.activity == expected_activity, \
            f"Expected {expected_activity} for {base64_status}, got {parsed.activity}"


def test_t2267_protobuf_status_with_timestamp(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 protobuf parsing for positioning codes with timestamps."""
    # These codes have embedded timestamps but should all parse as Positioning
    positioning_codes = [
        "DAi73ou93qHyzgFSAA==",
        "DAjE74KF76HyzgFSAA==",
        "DAiCobvM+KHyzgFSAA==",
    ]

    for code in positioning_codes:
        parsed = mock_t2267_robovac.parse_protobuf_status(code)
        assert parsed is not None, f"Failed to parse {code}"
        assert parsed.state == CleaningState.POSITIONING, \
            f"Expected POSITIONING for {code}, got {parsed.state}"


def test_t2267_protobuf_error_parsing(mock_t2267_robovac: RoboVac) -> None:
    """Test T2267 protobuf-based ERROR parsing."""
    # Positioning status sent on error channel should return None (no error)
    positioning_on_error = "DAi73ou93qHyzgFSAA=="
    result = mock_t2267_robovac.parse_protobuf_error(positioning_on_error)
    assert result is None, "Positioning status on error channel should return None"

    # Human-readable value for error should be "no_error" when no actual error
    hr_result = mock_t2267_robovac.getRoboVacHumanReadableValue(
        RobovacCommand.ERROR, positioning_on_error
    )
    assert hr_result == "no_error"


def test_t2267_human_readable_status(mock_t2267_robovac: RoboVac) -> None:
    """Test getRoboVacHumanReadableValue for STATUS uses protobuf."""
    # The human-readable value should come from protobuf parsing
    result = mock_t2267_robovac.getRoboVacHumanReadableValue(
        RobovacCommand.STATUS, "BgoAEAUyAA=="
    )
    assert result == "Cleaning"

    result = mock_t2267_robovac.getRoboVacHumanReadableValue(
        RobovacCommand.STATUS, "BBADGgA="
    )
    assert result == "Docked"
