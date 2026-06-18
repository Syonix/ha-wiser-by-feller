"""Tests for light platform entities (light.py) and OnOff switch entity (switch.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import DaliRgbw, DaliTw, Dim, OnOff
from aiowiserbyfeller.const import KIND_LIGHT, KIND_SWITCH
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBW_COLOR,
)

from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.light import (
    WiserDimEntity,
    WiserDimRgbwEntity,
    WiserDimTwEntity,
    WiserOnOffEntity,
)
from custom_components.wiser_by_feller.switch import WiserOnOffSwitchEntity
from custom_components.wiser_by_feller.util import (
    brightness_to_wiser,
    wiser_to_brightness,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_load(spec, kind=KIND_LIGHT, raw_state=None):
    load = MagicMock(spec=spec)
    load.id = 1
    load.name = "Test Light"
    load.device = "000004d7"
    load.room = None
    load.kind = kind
    load.sub_type = None
    load.raw_state = raw_state or {"bri": 5000}
    load.state = True
    load.async_switch_on = AsyncMock()
    load.async_switch_off = AsyncMock()
    load.async_set_bri = AsyncMock()
    load.async_set_bri_ct = AsyncMock()
    load.async_set_bri_rgbw = AsyncMock()
    return load


def _make_device():
    device = MagicMock()
    device.id = "000004d7"
    device.c = {
        "comm_ref": "926-3406.4.S.A.F",
        "comm_name": "Druckschalter 4K",
        "fw_version": "0x00500a28",
    }
    device.a = {
        "comm_ref": "3404.A",
        "comm_name": "Druckschalter 4K",
        "fw_version": "0x00501a30",
    }
    device.c_name = "Druckschalter 4K"
    device.a_name = "Druckschalter 4K"
    device.combined_serial_number = "011110_B_000064"
    device.outputs = [{}]
    return device


def _make_coordinator():
    coord = MagicMock(spec=WiserCoordinator)
    coord.gateway = MagicMock()
    coord.gateway.combined_serial_number = "20012161"
    coord.async_is_onoff_impulse_load = AsyncMock(return_value=False)
    return coord


# ── WiserOnOffEntity ──────────────────────────────────────────────────────────


def test_onoff_entity_is_on():
    """OnOff load state=True → entity is_on is True."""
    load = _make_load(OnOff)
    load.state = True
    entity = WiserOnOffEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_on is True


def test_onoff_entity_is_off():
    """OnOff load state=False → entity is_on is False."""
    load = _make_load(OnOff)
    load.state = False
    entity = WiserOnOffEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_on is False


async def test_onoff_turn_on_calls_api():
    """async_turn_on calls load.async_switch_on()."""
    load = _make_load(OnOff)
    entity = WiserOnOffEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on()
    load.async_switch_on.assert_called_once()


async def test_onoff_turn_off_calls_api():
    """async_turn_off calls load.async_switch_off()."""
    load = _make_load(OnOff)
    entity = WiserOnOffEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_off()
    load.async_switch_off.assert_called_once()


# ── WiserOnOffSwitchEntity ────────────────────────────────────────────────────


def test_onoff_switch_entity_is_on():
    """OnOff switch load state=True → entity is_on is True."""
    load = _make_load(OnOff, kind=KIND_SWITCH)
    load.state = True
    entity = WiserOnOffSwitchEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_on is True


async def test_onoff_switch_turn_on_calls_api():
    """async_turn_on on a switch entity calls load.async_switch_on()."""
    load = _make_load(OnOff, kind=KIND_SWITCH)
    entity = WiserOnOffSwitchEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on()
    load.async_switch_on.assert_called_once()


async def test_onoff_switch_turn_off_calls_api():
    """async_turn_off on a switch entity calls load.async_switch_off()."""
    load = _make_load(OnOff, kind=KIND_SWITCH)
    entity = WiserOnOffSwitchEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_off()
    load.async_switch_off.assert_called_once()


# ── WiserDimEntity ────────────────────────────────────────────────────────────


def test_dim_is_on_when_bri_positive():
    """Dim entity is_on is True when bri > 0."""
    load = _make_load(Dim, raw_state={"bri": 5000})
    entity = WiserDimEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_on is True


def test_dim_is_off_when_bri_zero():
    """Dim entity is_on is False when bri == 0."""
    load = _make_load(Dim, raw_state={"bri": 0})
    entity = WiserDimEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.is_on is False


def test_dim_brightness_conversion():
    """Dim entity brightness property converts Wiser bri via wiser_to_brightness."""
    raw_bri = 5000
    load = _make_load(Dim, raw_state={"bri": raw_bri})
    entity = WiserDimEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.brightness == wiser_to_brightness(raw_bri)


async def test_dim_turn_on_with_brightness_calls_set_bri():
    """async_turn_on with ATTR_BRIGHTNESS converts and calls load.async_set_bri."""
    load = _make_load(Dim, raw_state={"bri": 0})
    entity = WiserDimEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    load.async_set_bri.assert_called_once_with(brightness_to_wiser(128))


async def test_dim_turn_on_without_brightness_calls_switch_on():
    """async_turn_on without brightness falls back to load.async_switch_on."""
    load = _make_load(Dim, raw_state={"bri": 0})
    entity = WiserDimEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on()
    load.async_switch_on.assert_called_once()


# ── WiserDimTwEntity ──────────────────────────────────────────────────────────


def test_dim_tw_color_temp_from_raw_state():
    """Tunable-white entity reads color_temp_kelvin from raw_state['ct']."""
    load = _make_load(DaliTw, raw_state={"bri": 5000, "ct": 4000})
    entity = WiserDimTwEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.color_temp_kelvin == 4000


def test_dim_tw_brightness_from_raw_state():
    """Tunable-white entity brightness is converted from raw_state['bri']."""
    load = _make_load(DaliTw, raw_state={"bri": 5000, "ct": 4000})
    entity = WiserDimTwEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.brightness == wiser_to_brightness(5000)


async def test_dim_tw_turn_on_with_ct_calls_set_bri_ct():
    """async_turn_on with ATTR_COLOR_TEMP_KELVIN calls load.async_set_bri_ct."""
    load = _make_load(DaliTw, raw_state={"bri": 5000, "ct": 3000})
    entity = WiserDimTwEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 2700})
    load.async_set_bri_ct.assert_called_once()


# ── WiserDimRgbwEntity ────────────────────────────────────────────────────────


def test_dim_rgbw_color_tuple():
    """RGBW entity rgbw_color returns (r, g, b, w) tuple from raw_state."""
    raw_state = {"bri": 5000, "red": 255, "green": 128, "blue": 0, "white": 64}
    load = _make_load(DaliRgbw, raw_state=raw_state)
    entity = WiserDimRgbwEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.rgbw_color == (255, 128, 0, 64)


def test_dim_rgbw_color_none_when_missing():
    """RGBW entity rgbw_color is None when color keys are absent from raw_state."""
    raw_state = {"bri": 5000}
    load = _make_load(DaliRgbw, raw_state=raw_state)
    entity = WiserDimRgbwEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.rgbw_color is None


async def test_dim_rgbw_turn_on_with_color_calls_set_bri_rgbw():
    """async_turn_on with ATTR_RGBW_COLOR calls load.async_set_bri_rgbw."""
    raw_state = {"bri": 5000, "red": 0, "green": 0, "blue": 0, "white": 0}
    load = _make_load(DaliRgbw, raw_state=raw_state)
    entity = WiserDimRgbwEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_turn_on(**{ATTR_RGBW_COLOR: (255, 0, 0, 0)})
    load.async_set_bri_rgbw.assert_called_once()


# ── impulse load excluded from light platform ─────────────────────────────────


async def test_impulse_onoff_skipped_from_light(
    hass, mock_config_entry, mock_coordinator
):
    """Impulse OnOff loads must not appear in the light platform."""
    onoff_load = _make_load(OnOff, kind=KIND_LIGHT)
    onoff_load.id = 1

    mock_coordinator.loads = {1: onoff_load}
    mock_coordinator.states = {1: {"bri": 0}}
    mock_coordinator.devices = {onoff_load.device: _make_device()}
    mock_coordinator.rooms = {}
    # Mark load as impulse
    mock_coordinator.async_is_onoff_impulse_load = AsyncMock(return_value=True)

    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.wiser_by_feller.Auth"),
        patch("custom_components.wiser_by_feller.WiserByFellerAPI"),
        patch(
            "custom_components.wiser_by_feller.WiserCoordinator",
            return_value=mock_coordinator,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # No light entity should have been registered
    light_states = hass.states.async_entity_ids("light")
    assert len(light_states) == 0
