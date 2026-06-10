"""Tests for climate platform entities."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import HvacGroup
from aiowiserbyfeller.hvac import HvacChannelState
from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.wiser_by_feller.climate import WiserHvacGroupEntity, resolve_room
from custom_components.wiser_by_feller.coordinator import WiserCoordinator

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_hvac_group(
    loads=None, thermostat_ref=None, is_on=True, state=HvacChannelState.IDLE
):
    group = MagicMock(spec=HvacGroup)
    group.id = 10
    group.name = "Living Room HVAC"
    group.loads = loads or [1]
    group.thermostat_ref = thermostat_ref
    group.is_on = is_on
    group.state = state
    group.ambient_temperature = 21.5
    group.target_temperature = 22.0
    group.min_temperature = 5.0
    group.max_temperature = 30.0
    group.raw_state = {}
    group.flag = MagicMock(return_value=False)
    group.async_enable = AsyncMock()
    group.async_disable = AsyncMock()
    group.async_set_target_temperature = AsyncMock()
    return group


def _make_thermostat(device_id="0000f3a1"):
    device = MagicMock()
    device.id = device_id
    device.c = {
        "comm_ref": "9020.001.011",
        "comm_name": "Raumtemperatursensor",
        "fw_version": "0x00500a28",
    }
    device.a = {
        "comm_ref": "9020.001.011",
        "comm_name": "Raumtemperatursensor",
        "fw_version": "0x00500a28",
    }
    device.c_name = "Raumtemperatursensor"
    device.a_name = "Raumtemperatursensor"
    device.combined_serial_number = "018443_B_000099"
    device.outputs = []
    return device


def _make_coordinator(loads=None, rooms=None):
    coord = MagicMock(spec=WiserCoordinator)
    coord.gateway = MagicMock()
    coord.gateway.combined_serial_number = "20012161"
    coord.loads = loads or {}
    coord.rooms = rooms or {}
    return coord


# ── resolve_room ──────────────────────────────────────────────────────────────


def test_resolve_room_single_room_returns_room():
    """All loads in the same room → resolve_room returns that room dict."""
    load_a = MagicMock()
    load_a.room = 5
    load_b = MagicMock()
    load_b.room = 5
    rooms = {5: {"id": 5, "name": "Kitchen"}}
    coord = _make_coordinator(loads={1: load_a, 2: load_b}, rooms=rooms)

    group = _make_hvac_group(loads=[1, 2])
    room = resolve_room(coord, group)
    assert room == {"id": 5, "name": "Kitchen"}


def test_resolve_room_mixed_rooms_returns_none():
    """Loads spread across multiple rooms → resolve_room returns None."""
    load_a = MagicMock()
    load_a.room = 5
    load_b = MagicMock()
    load_b.room = 6
    rooms = {5: {"id": 5, "name": "Kitchen"}, 6: {"id": 6, "name": "Bedroom"}}
    coord = _make_coordinator(loads={1: load_a, 2: load_b}, rooms=rooms)

    group = _make_hvac_group(loads=[1, 2])
    room = resolve_room(coord, group)
    assert room is None


# ── WiserHvacGroupEntity ──────────────────────────────────────────────────────


def test_hvac_mode_heat_when_on():
    """HVAC group is_on=True → hvac_mode is HVACMode.HEAT."""
    group = _make_hvac_group(is_on=True)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.hvac_mode == HVACMode.HEAT


def test_hvac_mode_off_when_disabled():
    """HVAC group is_on=False → hvac_mode is HVACMode.OFF."""
    group = _make_hvac_group(is_on=False)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_action_heating():
    """HEATING state → hvac_action is HVACAction.HEATING."""
    group = _make_hvac_group(state=HvacChannelState.HEATING)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.hvac_action == HVACAction.HEATING


def test_hvac_action_idle():
    """IDLE state → hvac_action is HVACAction.IDLE."""
    group = _make_hvac_group(state=HvacChannelState.IDLE)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.hvac_action == HVACAction.IDLE


def test_hvac_action_off():
    """OFF state → hvac_action is HVACAction.OFF."""
    group = _make_hvac_group(state=HvacChannelState.OFF)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.hvac_action == HVACAction.OFF


def test_current_temperature():
    """current_temperature reflects the group's ambient_temperature."""
    group = _make_hvac_group()
    group.ambient_temperature = 20.5
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.current_temperature == 20.5


def test_target_temperature():
    """target_temperature reflects the group's target_temperature."""
    group = _make_hvac_group()
    group.target_temperature = 21.0
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.target_temperature == 21.0


def test_min_max_temp():
    """min_temp and max_temp reflect the group's temperature boundaries."""
    group = _make_hvac_group()
    group.min_temperature = 5.0
    group.max_temperature = 30.0
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.min_temp == 5.0
    assert entity.max_temp == 30.0


def test_temperature_step():
    """target_temperature_step is 0.5°C."""
    group = _make_hvac_group()
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    assert entity.target_temperature_step == 0.5


async def test_set_temperature_rounds_and_calls_api():
    """async_set_temperature rounds to 1 decimal and calls async_set_target_temperature."""
    group = _make_hvac_group()
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    await entity.async_set_temperature(temperature=21.567)
    group.async_set_target_temperature.assert_called_once_with(21.6)


async def test_set_temperature_none_is_noop():
    """async_set_temperature with temperature=None does not call the API."""
    group = _make_hvac_group()
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    await entity.async_set_temperature(temperature=None)
    group.async_set_target_temperature.assert_not_called()


async def test_set_hvac_mode_off_calls_disable():
    """Setting HVACMode.OFF calls group.async_disable()."""
    group = _make_hvac_group()
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    await entity.async_set_hvac_mode(HVACMode.OFF)
    group.async_disable.assert_called_once()


async def test_set_hvac_mode_heat_calls_enable():
    """Setting HVACMode.HEAT calls group.async_enable()."""
    group = _make_hvac_group(is_on=False)
    entity = WiserHvacGroupEntity(_make_coordinator(), group, _make_thermostat(), None)
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    group.async_enable.assert_called_once()


def test_unique_id_uses_thermostat_id():
    """Unique ID contains the thermostat device ID and 'hvac_group'."""
    thermostat = _make_thermostat("MY_THERM")
    group = _make_hvac_group()
    entity = WiserHvacGroupEntity(_make_coordinator(), group, thermostat, None)
    assert "MY_THERM" in entity.unique_id
    assert "hvac_group" in entity.unique_id


# ── setup skips groups without thermostat ─────────────────────────────────────


async def test_climate_setup_skips_group_without_thermostat(
    hass, mock_config_entry, mock_coordinator
):
    """HVAC groups with thermostat_ref=None are not created as climate entities."""
    # Group with thermostat_ref=None should be skipped
    group = _make_hvac_group(thermostat_ref=None)
    mock_coordinator.hvac_groups = {10: group}

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

    climate_states = hass.states.async_entity_ids("climate")
    assert len(climate_states) == 0
