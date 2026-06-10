"""Tests for cover platform entities."""

from unittest.mock import AsyncMock, MagicMock

from aiowiserbyfeller import Motor
from aiowiserbyfeller.const import KIND_AWNING, KIND_VENETIAN_BLINDS
from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntityFeature,
)

from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.cover import (
    WiserCoverEntity,
    WiserRelayEntity,
    WiserTiltableCoverEntity,
)
from custom_components.wiser_by_feller.util import (
    cover_position_to_wiser,
    cover_tilt_to_wiser,
    wiser_to_cover_position,
    wiser_to_cover_tilt,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_motor(kind=None, sub_type=None, state=None):
    load = MagicMock(spec=Motor)
    load.id = 1
    load.device = "00000679"
    load.room = None
    load.kind = kind
    load.sub_type = sub_type
    load.state = state or {"level": 0, "tilt": 0, "moving": "stop"}
    load.raw_state = load.state
    load.async_set_level = AsyncMock()
    load.async_set_tilt = AsyncMock()
    load.async_stop = AsyncMock()
    return load


def _make_device():
    device = MagicMock()
    device.id = "00000679"
    device.c = {
        "comm_ref": "926-3406.4.S.A.F",
        "comm_name": "Motorsteuerung 1K",
        "fw_version": "0x00500a28",
    }
    device.a = {
        "comm_ref": "3406.A",
        "comm_name": "Motorsteuerung 1K",
        "fw_version": "0x00500a28",
    }
    device.c_name = "Motorsteuerung 1K"
    device.a_name = "Motorsteuerung 1K"
    device.combined_serial_number = "018443_B_000050"
    device.outputs = [{}]
    return device


def _make_coordinator():
    coord = MagicMock(spec=WiserCoordinator)
    coord.gateway = MagicMock()
    coord.gateway.combined_serial_number = "20012161"
    return coord


# ── WiserRelayEntity ──────────────────────────────────────────────────────────


def test_relay_entity_supported_features():
    """Relay entity supports OPEN, CLOSE, STOP but not SET_POSITION."""
    load = _make_motor(sub_type="relay")
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    features = entity.supported_features
    assert CoverEntityFeature.OPEN in features
    assert CoverEntityFeature.CLOSE in features
    assert CoverEntityFeature.STOP in features
    assert CoverEntityFeature.SET_POSITION not in features


def test_relay_entity_no_position():
    """Relay entity does not advertise the SET_POSITION feature."""
    load = _make_motor(sub_type="relay")
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    assert CoverEntityFeature.SET_POSITION not in entity.supported_features


def test_relay_is_closed_when_level_10000():
    """Relay at Wiser level 10000 (fully closed) → is_closed is True."""
    load = _make_motor(sub_type="relay", state={"level": 10000, "moving": "stop"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_closed is True


def test_relay_is_closed_false_when_level_zero():
    """Relay at Wiser level 0 (fully open) → is_closed is False."""
    load = _make_motor(sub_type="relay", state={"level": 0, "moving": "stop"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_closed is False


def test_relay_is_opening():
    """Relay moving up → is_opening is True and is_closing is False."""
    load = _make_motor(sub_type="relay", state={"level": 5000, "moving": "up"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_opening is True
    assert entity.is_closing is False


def test_relay_is_closing():
    """Relay moving down → is_closing is True and is_opening is False."""
    load = _make_motor(sub_type="relay", state={"level": 5000, "moving": "down"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_closing is True
    assert entity.is_opening is False


async def test_relay_open_calls_set_level_zero():
    """async_open_cover sets level to 0 (fully open in Wiser coordinates)."""
    load = _make_motor(sub_type="relay", state={"level": 10000, "moving": "stop"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_open_cover()
    load.async_set_level.assert_called_once_with(0)


async def test_relay_close_calls_set_level_10000():
    """async_close_cover sets level to 10000 (fully closed in Wiser coordinates)."""
    load = _make_motor(sub_type="relay", state={"level": 0, "moving": "stop"})
    entity = WiserRelayEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_close_cover()
    load.async_set_level.assert_called_once_with(10000)


# ── WiserCoverEntity ──────────────────────────────────────────────────────────


def test_cover_entity_has_set_position_feature():
    """Cover entity advertises the SET_POSITION feature."""
    load = _make_motor(kind=None, state={"level": 5000, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert CoverEntityFeature.SET_POSITION in entity.supported_features


def test_cover_position_converted_correctly():
    """current_cover_position is the Wiser level converted via wiser_to_cover_position."""
    load = _make_motor(state={"level": 5000, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.current_cover_position == wiser_to_cover_position(5000)


def test_cover_is_closed_at_ha_zero():
    """Wiser level 10000 maps to HA position 0 and is_closed is True."""
    # HA 0 corresponds to Wiser 10000
    load = _make_motor(state={"level": 10000, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.current_cover_position == 0
    assert entity.is_closed is True


def test_cover_awning_device_class():
    """Cover with kind KIND_AWNING has device_class AWNING."""
    load = _make_motor(kind=KIND_AWNING, state={"level": 0, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.device_class == CoverDeviceClass.AWNING


def test_cover_shade_device_class_default():
    """Cover with no kind defaults to device_class SHADE."""
    load = _make_motor(kind=None, state={"level": 0, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.device_class == CoverDeviceClass.SHADE


async def test_set_cover_position_calls_api_with_converted_value():
    """async_set_cover_position converts HA position to Wiser level and calls the API."""
    load = _make_motor(state={"level": 5000, "moving": "stop"})
    entity = WiserCoverEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_set_cover_position(**{ATTR_POSITION: 50})
    expected_level = cover_position_to_wiser(50)
    load.async_set_level.assert_called_once_with(expected_level)


# ── WiserTiltableCoverEntity ──────────────────────────────────────────────────


def test_tiltable_has_tilt_features():
    """Venetian blind entity supports SET_TILT_POSITION, OPEN_TILT, CLOSE_TILT."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 0, "tilt": 5, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert CoverEntityFeature.SET_TILT_POSITION in entity.supported_features
    assert CoverEntityFeature.OPEN_TILT in entity.supported_features
    assert CoverEntityFeature.CLOSE_TILT in entity.supported_features


def test_tiltable_device_class_is_blind():
    """Venetian blind entity has device_class BLIND."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 0, "tilt": 0, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.device_class == CoverDeviceClass.BLIND


def test_tiltable_tilt_position_converted():
    """current_cover_tilt_position is the Wiser tilt converted via wiser_to_cover_tilt."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 0, "tilt": 5, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.current_cover_tilt_position == wiser_to_cover_tilt(5)


async def test_set_tilt_position_calls_api():
    """async_set_cover_tilt_position converts HA tilt to Wiser and calls the API."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 0, "tilt": 0, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 50})
    load.async_set_tilt.assert_called_once_with(cover_tilt_to_wiser(50))


def test_tiltable_is_closed_requires_both_zero():
    """Venetian blind is_closed only when both position AND tilt are at zero (HA)."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 10000, "tilt": 0, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    # position=0 (Wiser 10000 → HA 0) AND tilt=0 → is_closed True
    assert entity.is_closed is True


def test_tiltable_not_closed_when_only_position_zero():
    """Venetian blind is_closed is False when position is 0 but tilt is non-zero."""
    load = _make_motor(
        kind=KIND_VENETIAN_BLINDS, state={"level": 10000, "tilt": 5, "moving": "stop"}
    )
    entity = WiserTiltableCoverEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_closed is False
