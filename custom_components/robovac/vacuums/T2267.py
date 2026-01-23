"""RoboVac L60 (T2267) - Protobuf-based model."""
from homeassistant.components.vacuum import VacuumEntityFeature
from .base import RoboVacEntityFeature, RobovacCommand, ProtobufVacuumModel


class T2267(ProtobufVacuumModel):
    """T2267 vacuum model using protobuf for status parsing."""

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

    commands = {
        RobovacCommand.MODE: {
            "code": 152,
            "values": {
                "auto": "BBoCCAE=",
                "pause": "AggN",
                "spot": "BggDMgIIAQ==",
                "return": "AggG",
                "resume": "AggO",
                "stop": "AggM",
            },
        },
        RobovacCommand.STATUS: {
            "code": 153,
        },
        RobovacCommand.DIRECTION: {
            "code": 155,
            "values": {
                "brake": "AggA",
                "forward": "AggB",
                "back": "AggC",
                "left": "AggD",
                "right": "AggE",
            },
        },
        RobovacCommand.START_PAUSE: {
            "code": 156,
        },
        RobovacCommand.DO_NOT_DISTURB: {
            "code": 157,
        },
        RobovacCommand.FAN_SPEED: {
            "code": 158,
            "values": {
                "quiet": "Quiet",
                "standard": "Standard",
                "turbo": "Turbo",
                "max": "Max",
                "boost_iq": "Boost_IQ",
            },
        },
        RobovacCommand.BOOST_IQ: {
            "code": 159,
        },
        RobovacCommand.LOCATE: {
            "code": 160,
        },
        RobovacCommand.BATTERY: {
            "code": 163,
        },
        RobovacCommand.CONSUMABLES: {
            "code": 168,
        },
        RobovacCommand.RETURN_HOME: {
            "code": 173,
        },
        RobovacCommand.ERROR: {
            "code": 177,
        }
    }
