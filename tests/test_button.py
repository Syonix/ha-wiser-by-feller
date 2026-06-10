"""Tests for button platform entities."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import HvacGroup, Load, OnOff
from aiowiserbyfeller.const import BUTTON_ON, EVENT_CLICK
from aiowiserbyfeller.enum import BlinkPattern

from custom_components.wiser_by_feller.button import (
    WiserClimatePingEntity,
    WiserImpulseEntity,
    WiserPingEntity,
)
from custom_components.wiser_by_feller.const import HA_BLUE
from custom_components.wiser_by_feller.coordinator import WiserCoordinator

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_load(spec=Load, load_id=1, device_id="000004d7"):
    load = MagicMock(spec=spec)
    load.id = load_id
    load.name = "Test Load"
    load.device = device_id
    load.room = None
    load.raw_state = {"bri": 0}
    load.async_ping = AsyncMock()
    load.async_ctrl = AsyncMock()
    return load


def _make_device(device_id="000004d7", has_outputs=True):
    device = MagicMock()
    device.id = device_id
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
    device.outputs = [{}] if has_outputs else []
    return device


def _make_coordinator(loads=None, devices=None):
    coord = MagicMock(spec=WiserCoordinator)
    gw = MagicMock()
    gw.combined_serial_number = "20012161"
    coord.gateway = gw
    coord.async_ping_device = AsyncMock()
    coord.loads = loads or {}
    coord.devices = devices or {}
    coord.assigned_thermostats = {}
    return coord


def _make_hvac_group(load_ids=None, thermostat_ref=None):
    group = MagicMock(spec=HvacGroup)
    group.id = 10
    group.name = "HVAC Group"
    group.loads = load_ids or [1]
    group.thermostat_ref = thermostat_ref
    group.raw_state = {}
    return group


# ── WiserPingEntity ───────────────────────────────────────────────────────────


def test_ping_entity_unique_id_has_identify_suffix():
    """Ping entity unique_id ends with the '_identify' suffix."""
    load = _make_load()
    entity = WiserPingEntity(_make_coordinator(), load, _make_device(), None)
    assert entity.unique_id.endswith("_identify")


async def test_ping_press_with_load_calls_async_ping():
    """Pressing a load-based ping entity calls load.async_ping with correct args."""
    load = _make_load()
    entity = WiserPingEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_press()
    load.async_ping.assert_called_once_with(10000, BlinkPattern.RAMP, HA_BLUE)


async def test_ping_press_without_load_calls_coordinator_ping_device():
    """Pressing a device-only ping entity calls coordinator.async_ping_device."""
    device = _make_device(has_outputs=False)
    coord = _make_coordinator(devices={device.id: device})
    entity = WiserPingEntity(coord, None, device, None)
    await entity.async_press()
    coord.async_ping_device.assert_called_once_with(device.id)


# ── WiserImpulseEntity ────────────────────────────────────────────────────────


def test_impulse_entity_created_for_impulse_load():
    """WiserImpulseEntity can be instantiated for an OnOff impulse load."""
    load = _make_load(OnOff)
    entity = WiserImpulseEntity(_make_coordinator(), load, _make_device(), None)
    assert entity is not None


async def test_impulse_press_calls_async_ctrl():
    """Pressing an impulse entity calls load.async_ctrl(BUTTON_ON, EVENT_CLICK)."""
    load = _make_load(OnOff)
    entity = WiserImpulseEntity(_make_coordinator(), load, _make_device(), None)
    await entity.async_press()
    load.async_ctrl.assert_called_once_with(BUTTON_ON, EVENT_CLICK)


# ── WiserClimatePingEntity ────────────────────────────────────────────────────


async def test_climate_ping_presses_all_loads_and_thermostat():
    """Pressing a climate ping entity pings every group load and the thermostat device."""
    load1 = _make_load(load_id=1)
    load2 = _make_load(load_id=2)
    thermostat = _make_device("THERM001")

    coord = _make_coordinator(
        loads={1: load1, 2: load2},
        devices={thermostat.id: thermostat},
    )

    thermostat_ref = MagicMock()
    thermostat_ref.unprefixed_address = "THERM001"
    group = _make_hvac_group(load_ids=[1, 2], thermostat_ref=thermostat_ref)

    entity = WiserClimatePingEntity(coord, group, thermostat, None)
    await entity.async_press()

    load1.async_ping.assert_called_once_with(10000, BlinkPattern.RAMP, HA_BLUE)
    load2.async_ping.assert_called_once_with(10000, BlinkPattern.RAMP, HA_BLUE)
    coord.async_ping_device.assert_called_once_with(thermostat.id)


def test_climate_ping_unique_id_has_hvac_group_identify():
    """Climate ping entity unique_id contains 'hvac_group_identify'."""
    thermostat = _make_device("THERM001")
    thermostat_ref = MagicMock()
    thermostat_ref.unprefixed_address = "THERM001"
    group = _make_hvac_group(thermostat_ref=thermostat_ref)

    entity = WiserClimatePingEntity(_make_coordinator(), group, thermostat, None)
    assert "hvac_group_identify" in entity.unique_id


# ── button platform setup ─────────────────────────────────────────────────────


async def test_button_platform_creates_ping_entity_per_load(
    hass, mock_config_entry, mock_coordinator
):
    """Button platform setup creates at least one ping entity for a non-impulse load."""
    load = _make_load()
    device = _make_device()
    mock_coordinator.loads = {load.id: load}
    mock_coordinator.states = {load.id: {"bri": 0}}
    mock_coordinator.devices = {device.id: device}
    mock_coordinator.rooms = {}
    mock_coordinator.async_is_onoff_impulse_load = AsyncMock(return_value=False)

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

    button_states = hass.states.async_entity_ids("button")
    assert len(button_states) >= 1
