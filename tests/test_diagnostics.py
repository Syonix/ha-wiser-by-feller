"""Tests for diagnostics support."""

from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED

from custom_components.wiser_by_feller.const import DOMAIN
from custom_components.wiser_by_feller.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_load_with_raw(load_id=1):
    load = MagicMock()
    load.id = load_id
    load.raw_data = {"id": load_id, "sn": "SHOULD_BE_REDACTED", "name": "Light"}
    return load


def _make_device_with_raw(device_id="000004d7"):
    device = MagicMock()
    device.id = device_id
    device.raw_data = {"id": device_id, "serial_nr": "SHOULD_BE_REDACTED"}
    return device


def _make_scene_with_raw(scene_id=1):
    scene = MagicMock()
    scene.id = scene_id
    scene.raw_data = {"id": scene_id, "name": "Movie Night"}
    return scene


def _make_button_with_raw(button_id=1, device="000004d7"):
    button = MagicMock()
    button.id = button_id
    button.device = device
    button.raw_data = {
        "id": button_id,
        "device": device,
        "channel": 0,
        "sn": "SHOULD_BE_REDACTED",
    }
    return button


def _make_with_raw(obj_id, raw):
    item = MagicMock()
    item.id = obj_id
    item.raw_data = raw
    return item


def _build_coordinator(entry):
    coord = MagicMock()
    coord.loads = {1: _make_load_with_raw(1)}
    coord.devices = {"000004d7": _make_device_with_raw("000004d7")}
    coord.rooms = {5: {"id": 5, "name": "Living Room"}}
    coord.scenes = {1: _make_scene_with_raw(1)}
    coord.gateway_info = {
        "api": "6.0",
        "sw": "1.2.3",
        "sn": "SHOULD_BE_REDACTED",
    }
    # sensors live in both coordinator.sensors and (as full raw_data)
    # coordinator.states; load 1 is a plain state value.
    coord.sensors = {42: _make_with_raw(42, {"id": 42, "type": "temperature"})}
    coord.states = {
        1: {"id": 1, "bri": 5000},
        42: {"id": 42, "type": "temperature", "value": 21.5},
    }
    coord.system_health = {"mem_free": 1234, "uptime": 5678}
    coord.system_flags = [_make_with_raw(1, {"id": 1, "symbol": "x", "value": 0})]
    coord.jobs = {1: _make_with_raw(1, {"id": 1, "target_states": []})}
    coord.hvac_groups = {1: _make_with_raw(1, {"id": 1, "name": "Heating"})}
    coord.managed_buttons = {
        1: _make_button_with_raw(1, "000004d7"),
        2: _make_button_with_raw(2, "deadbeef"),
    }
    return coord


# ── TO_REDACT list ────────────────────────────────────────────────────────────


def test_to_redact_includes_token():
    """TO_REDACT must contain 'token' so API tokens are hidden in diagnostics."""
    assert "token" in TO_REDACT


def test_to_redact_includes_sn():
    """TO_REDACT must contain 'sn' so gateway serial numbers are hidden."""
    assert "sn" in TO_REDACT


def test_to_redact_includes_serial_nr():
    """TO_REDACT must contain 'serial_nr' for device serial number redaction."""
    assert "serial_nr" in TO_REDACT


def test_to_redact_includes_serial_number():
    """TO_REDACT must contain 'serial_number' for long-form serial field."""
    assert "serial_number" in TO_REDACT


# ── async_get_config_entry_diagnostics ───────────────────────────────────────


async def test_config_entry_diagnostics_structure(hass, mock_config_entry):
    """Config entry diagnostics must return all six top-level keys."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "entry_data" in result
    assert "gateway_info" in result
    assert "loads" in result
    assert "rooms" in result
    assert "devices" in result
    assert "scenes" in result


async def test_config_entry_diagnostics_includes_extra_sections(
    hass, mock_config_entry
):
    """Config entry diagnostics must include the extended debug sections."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    for key in (
        "coordinator",
        "system_health",
        "system_flags",
        "states",
        "jobs",
        "hvac_groups",
        "managed_buttons",
    ):
        assert key in result

    # The coordinator meta section carries runtime/capability info and counts.
    assert "counts" in result["coordinator"]
    assert result["coordinator"]["counts"]["managed_buttons"] == 2

    # Every managed button is present at the config-entry level.
    assert len(result["managed_buttons"]) == 2


async def test_config_entry_diagnostics_states_excludes_sensors(
    hass, mock_config_entry
):
    """Sensor values must appear only in 'sensors', not duplicated in 'states'."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Load state stays in 'states'; sensor (id 42) is filtered out.
    assert 1 in result["states"]
    assert 42 not in result["states"]
    # The sensor is still present in the dedicated 'sensors' section.
    assert any(sensor["id"] == 42 for sensor in result["sensors"])


async def test_config_entry_diagnostics_redacts_sn_in_managed_buttons(
    hass, mock_config_entry
):
    """Button 'sn' fields must not appear in plain text within managed_buttons."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "SHOULD_BE_REDACTED" not in str(result["managed_buttons"])


async def test_config_entry_diagnostics_redacts_api_host(hass, mock_config_entry):
    """The gateway 'api_host' (IP address) must be redacted in coordinator meta."""
    coord = _build_coordinator(mock_config_entry)
    coord.api_host = "192.168.1.50"
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["coordinator"]["api_host"] == REDACTED


async def test_config_entry_diagnostics_redacts_token(hass, mock_config_entry):
    """The 'token' key in entry_data must be redacted."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    # entry.data contains "token" which should be redacted
    assert result["entry_data"].get("token") == REDACTED


async def test_config_entry_diagnostics_redacts_sn_in_gateway_info(
    hass, mock_config_entry
):
    """Gateway 'sn' field must not appear in plain text within gateway_info."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "SHOULD_BE_REDACTED" not in str(result["gateway_info"])


async def test_config_entry_diagnostics_redacts_sn_in_loads(hass, mock_config_entry):
    """Load 'sn' fields must not appear in plain text within the loads output."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "SHOULD_BE_REDACTED" not in str(result["loads"])


# ── async_get_device_diagnostics ─────────────────────────────────────────────


async def test_device_diagnostics_gateway_device(hass, mock_config_entry):
    """Gateway device → returns gateway_info + scenes."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    # Create a mock DeviceEntry for the gateway
    device_entry = MagicMock()
    device_entry.name = f"{mock_config_entry.title} µGateway"
    device_entry.identifiers = {(DOMAIN, "GW_SN")}
    device_entry.json_repr = '{"name": "Test Wiser µGateway", "identifiers": []}'

    result = await async_get_device_diagnostics(hass, mock_config_entry, device_entry)

    assert "gateway_info" in result
    assert "scenes" in result
    assert "device" in result


async def test_device_diagnostics_regular_device(hass, mock_config_entry):
    """Regular device → returns device_data."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    # Create a mock DeviceEntry for a regular device (not gateway)
    device_entry = MagicMock()
    device_entry.name = "Living Room Dimmer"
    device_entry.identifiers = {(DOMAIN, "000004d7_0")}
    device_entry.json_repr = '{"name": "Living Room Dimmer", "identifiers": []}'

    result = await async_get_device_diagnostics(hass, mock_config_entry, device_entry)

    assert "device_data" in result
    assert "device" in result
    assert "gateway_info" not in result


async def test_device_diagnostics_includes_only_own_buttons(hass, mock_config_entry):
    """Regular device → managed_buttons limited to buttons on that device."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    device_entry = MagicMock()
    device_entry.name = "Living Room Dimmer"
    device_entry.identifiers = {(DOMAIN, "000004d7_0")}
    device_entry.json_repr = '{"name": "Living Room Dimmer", "identifiers": []}'

    result = await async_get_device_diagnostics(hass, mock_config_entry, device_entry)

    assert "managed_buttons" in result
    # Only button 1 belongs to device 000004d7; button 2 is on another device.
    assert len(result["managed_buttons"]) == 1
    assert result["managed_buttons"][0]["id"] == 1


async def test_device_diagnostics_gateway_includes_health(hass, mock_config_entry):
    """Gateway device → includes coordinator meta and system health/flags."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    device_entry = MagicMock()
    device_entry.name = f"{mock_config_entry.title} µGateway"
    device_entry.identifiers = {(DOMAIN, "GW_SN")}
    device_entry.json_repr = '{"name": "Test Wiser µGateway", "identifiers": []}'

    result = await async_get_device_diagnostics(hass, mock_config_entry, device_entry)

    assert "coordinator" in result
    assert "system_health" in result
    assert "system_flags" in result


async def test_device_diagnostics_redacts_serial_in_device_data(
    hass, mock_config_entry
):
    """Device 'serial_nr' must not appear in plain text within device_data."""
    coord = _build_coordinator(mock_config_entry)
    mock_config_entry.runtime_data = coord
    mock_config_entry.add_to_hass(hass)

    device_entry = MagicMock()
    device_entry.name = "Some Device"
    device_entry.identifiers = {(DOMAIN, "000004d7_0")}
    device_entry.json_repr = '{"name": "Some Device", "identifiers": []}'

    result = await async_get_device_diagnostics(hass, mock_config_entry, device_entry)
    assert "SHOULD_BE_REDACTED" not in str(result["device_data"])
