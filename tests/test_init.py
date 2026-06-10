"""Tests for integration setup/teardown (__init__.py)."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.wiser_by_feller import async_setup_gateway
from custom_components.wiser_by_feller.const import DOMAIN

# ── setup ────────────────────────────────────────────────────────────────────


async def test_setup_entry_sets_runtime_data(hass, setup_integration, mock_coordinator):
    """async_setup_entry stores the coordinator in entry.runtime_data."""
    entry = setup_integration
    assert entry.runtime_data is mock_coordinator


async def test_setup_entry_calls_ws_init(hass, setup_integration, mock_coordinator):
    """async_setup_entry calls ws_init() to start the WebSocket connection."""
    mock_coordinator.ws_init.assert_called_once()


async def test_setup_entry_calls_first_refresh(
    hass, setup_integration, mock_coordinator
):
    """async_setup_entry triggers an initial coordinator refresh."""
    mock_coordinator.async_config_entry_first_refresh.assert_called_once()


async def test_setup_entry_forwards_all_platforms(
    hass, setup_integration, mock_config_entry
):
    """All platforms are forwarded and the config entry is in LOADED state."""
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    assert entry.state == ConfigEntryState.LOADED


async def test_setup_entry_registers_status_light_service(hass, setup_integration):
    """async_setup_entry registers the 'status_light' service under the domain."""
    assert hass.services.has_service(DOMAIN, "status_light")


# ── gateway registration ──────────────────────────────────────────────────────


async def test_setup_gateway_registers_device(
    hass, mock_config_entry, mock_coordinator, mock_gateway
):
    """async_setup_gateway creates a device registry entry for the µGateway."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.wiser_by_feller.Auth"),
        patch("custom_components.wiser_by_feller.WiserByFellerAPI"),
        patch(
            "custom_components.wiser_by_feller.WiserCoordinator",
            return_value=mock_coordinator,
        ),
        patch(
            "custom_components.wiser_by_feller.parse_wiser_device_ref_c",
            return_value={"generation": "Gen B"},
        ),
    ):
        await async_setup_gateway(hass, mock_config_entry, mock_coordinator)

    registry = dr.async_get(hass)
    device = registry.async_get_device({(DOMAIN, mock_gateway.combined_serial_number)})
    assert device is not None


async def test_setup_gateway_missing_uses_fallback(
    hass, mock_config_entry, mock_coordinator
):
    """When gateway is None, device is registered with title as identifier and 'Unknown µGateway' name."""
    mock_coordinator.gateway = None
    mock_config_entry.add_to_hass(hass)

    await async_setup_gateway(hass, mock_config_entry, mock_coordinator)

    registry = dr.async_get(hass)
    device = registry.async_get_device({(DOMAIN, mock_config_entry.title)})
    assert device is not None
    assert device.name == "Unknown µGateway"


# ── unload ────────────────────────────────────────────────────────────────────


async def test_unload_entry_calls_ws_close(hass, setup_integration, mock_coordinator):
    """async_unload_entry calls coordinator.ws_close() to shut down WebSocket."""
    entry = setup_integration
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_coordinator.ws_close.assert_called_once()


async def test_unload_entry_removes_service(hass, setup_integration):
    """async_unload_entry removes the 'status_light' service from hass.services."""
    entry = setup_integration
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "status_light")
