"""Tests for integration setup/teardown (__init__.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import UnsuccessfulRequest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wiser_by_feller import (
    async_remove_stale_devices,
    async_setup_gateway,
)
from custom_components.wiser_by_feller.const import (
    CONF_IMPORTUSER,
    DOMAIN,
    IMPORT_USER_UNKNOWN,
)

# ── setup ────────────────────────────────────────────────────────────────────


async def test_setup_entry_sets_runtime_data(hass, setup_integration, mock_coordinator):
    """async_setup_entry stores the coordinator in entry.runtime_data."""
    entry = setup_integration
    assert entry.runtime_data is mock_coordinator


async def test_setup_entry_backfills_unknown_import_user(hass, setup_integration):
    """Legacy entries without an import user are marked unknown, not guessed."""
    entry = setup_integration
    assert entry.data[CONF_IMPORTUSER] == IMPORT_USER_UNKNOWN


async def test_setup_entry_keeps_existing_import_user(
    hass, mock_config_entry, mock_coordinator
):
    """A stored import user is preserved and never overwritten on setup."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_IMPORTUSER: "installer"},
    )
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

    assert mock_config_entry.data[CONF_IMPORTUSER] == "installer"


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
    """async_setup registers the 'status_light' service under the domain."""
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


# ── stale device cleanup ──────────────────────────────────────────────────────


async def test_remove_stale_devices_removes_orphan(
    hass, mock_config_entry, mock_coordinator
):
    """Devices in the registry whose identifier is no longer in the coordinator are removed."""
    mock_config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)

    stale = registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "stale_device_001")},
    )

    mock_coordinator.loads = {}
    mock_coordinator.devices = {}
    mock_coordinator.hvac_groups = {}

    await async_remove_stale_devices(hass, mock_config_entry, mock_coordinator)

    assert registry.async_get(stale.id) is None


async def test_remove_stale_devices_keeps_gateway(
    hass, mock_config_entry, mock_coordinator
):
    """The gateway device entry is preserved when the gateway is still present."""
    mock_config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)

    gateway_device = registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, mock_coordinator.gateway.combined_serial_number)},
    )

    await async_remove_stale_devices(hass, mock_config_entry, mock_coordinator)

    assert registry.async_get(gateway_device.id) is not None


async def test_remove_stale_devices_keeps_known_load(
    hass, mock_config_entry, mock_coordinator
):
    """A device whose identifier matches an active load is not removed."""
    mock_config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)

    load = MagicMock()
    load.device = "00000679"
    load.channel = 0
    mock_coordinator.loads = {1: load}

    known = registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "00000679_0")},
    )

    await async_remove_stale_devices(hass, mock_config_entry, mock_coordinator)

    assert registry.async_get(known.id) is not None


# ── unload ────────────────────────────────────────────────────────────────────


async def test_unload_entry_calls_ws_close(hass, setup_integration, mock_coordinator):
    """async_unload_entry calls coordinator.ws_close() to shut down WebSocket."""
    entry = setup_integration
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_coordinator.ws_close.assert_called_once()


async def test_unload_entry_keeps_services(hass, setup_integration):
    """async_unload_entry does not remove any service.

    All services are registered once in async_setup (not per config entry) so
    they persist as long as the integration is loaded, regardless of how many
    entries are active.
    """
    entry = setup_integration
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "status_light")
    assert hass.services.has_service(DOMAIN, "set_button_led_override")
    assert hass.services.has_service(DOMAIN, "clear_button_led_override")
    assert hass.services.has_service(DOMAIN, "find_button")


# ── find_button service ───────────────────────────────────────────────────────

_MANAGED_FIELDS = {
    "room_name": "Living Room",
    "device_name": "Dimmer Plus",
    "scene_name": None,
}
_EMPTY_FIELDS = {"room_name": None, "device_name": None, "scene_name": None}


async def test_find_button_service_is_registered(hass, setup_integration):
    """find_button service is registered after setup."""
    assert hass.services.has_service(DOMAIN, "find_button")


async def test_find_button_managed_button_returns_fields(
    hass, setup_integration, mock_coordinator
):
    """Managed button: response contains button_id, device, channel, and resolved fields."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": 123, "device": "00019edc", "channel": 0}
    )
    mock_coordinator.resolve_managed_button_fields.return_value = _MANAGED_FIELDS
    response = await hass.services.async_call(
        DOMAIN, "find_button", {}, blocking=True, return_response=True
    )

    assert response["button_id"] == 123
    assert response["device"] == "00019edc"
    assert response["channel"] == 0
    assert response["room_name"] == "Living Room"
    assert response["device_name"] == "Dimmer Plus"
    assert response["scene_name"] is None
    assert "note" not in response


async def test_find_button_managed_button_returns_no_note(
    hass, setup_integration, mock_coordinator
):
    """Managed button responses never carry a note field."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": 5, "device": "aabbccdd", "channel": 0}
    )
    mock_coordinator.resolve_managed_button_fields.return_value = _EMPTY_FIELDS
    response = await hass.services.async_call(
        DOMAIN, "find_button", {}, blocking=True, return_response=True
    )

    assert "note" not in response


async def test_find_button_unmanaged_button_raises(
    hass, setup_integration, mock_coordinator
):
    """Unmanaged button raises a validation error pointing to the docs."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": None, "device": "00019edc", "channel": 0}
    )
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            DOMAIN, "find_button", {}, blocking=True, return_response=True
        )

    assert exc.value.translation_key == "unmanaged_button"


# ── set_button_led_override / clear_button_led_override error handling ────────


async def test_set_button_led_override_raises_service_error_on_api_failure(
    hass, setup_integration, mock_coordinator
):
    """set_button_led_override raises ServiceValidationError when the API returns an error."""
    mock_coordinator.api.async_set_button_led = AsyncMock(
        side_effect=UnsuccessfulRequest("SmartButton 43 not found")
    )
    with pytest.raises(ServiceValidationError, match="SmartButton 43 not found"):
        await hass.services.async_call(
            DOMAIN,
            "set_button_led_override",
            {"button_id": 43, "led_index": "0", "rgb_color": [255, 0, 0]},
            blocking=True,
        )


async def test_clear_button_led_override_raises_service_error_on_api_failure(
    hass, setup_integration, mock_coordinator
):
    """clear_button_led_override raises ServiceValidationError when the API returns an error."""
    mock_coordinator.api.async_set_button_led = AsyncMock(
        side_effect=UnsuccessfulRequest("SmartButton 43 not found")
    )
    with pytest.raises(ServiceValidationError, match="SmartButton 43 not found"):
        await hass.services.async_call(
            DOMAIN,
            "clear_button_led_override",
            {"button_id": 43, "led_index": "0"},
            blocking=True,
        )


# ── gateway selection for button services ─────────────────────────────────────


async def test_button_service_uses_explicit_gateway(
    hass, setup_integration, mock_coordinator
):
    """An explicit config_entry_id routes the call to that gateway's coordinator."""
    entry = setup_integration
    mock_coordinator.api.async_set_button_led = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        "set_button_led_override",
        {
            "config_entry_id": entry.entry_id,
            "button_id": 7,
            "led_index": "0",
            "rgb_color": [1, 2, 3],
        },
        blocking=True,
    )

    mock_coordinator.api.async_set_button_led.assert_awaited_once()


async def test_button_service_unknown_gateway_raises(hass, setup_integration):
    """An unknown config_entry_id raises a validation error."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_button_led_override",
            {
                "config_entry_id": "does-not-exist",
                "button_id": 7,
                "led_index": "0",
                "rgb_color": [1, 2, 3],
            },
            blocking=True,
        )


async def test_button_service_requires_gateway_when_multiple(
    hass, setup_integration, mock_coordinator
):
    """With several µGateways loaded and no selection, the service errors clearly."""
    # A first gateway is already loaded via setup_integration; add a second.
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Second Wiser",
        data={"host": "192.168.1.101", "token": "t"},
        unique_id="SECOND_SN",
    )
    second.add_to_hass(hass)
    with (
        patch("custom_components.wiser_by_feller.Auth"),
        patch("custom_components.wiser_by_feller.WiserByFellerAPI"),
        patch(
            "custom_components.wiser_by_feller.WiserCoordinator",
            return_value=mock_coordinator,
        ),
    ):
        await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="Multiple"):
        await hass.services.async_call(
            DOMAIN,
            "set_button_led_override",
            {"button_id": 1, "led_index": "0", "rgb_color": [255, 0, 0]},
            blocking=True,
        )
