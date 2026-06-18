"""Tests for integration setup/teardown (__init__.py)."""

from unittest.mock import AsyncMock, patch

from aiowiserbyfeller import UnsuccessfulRequest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest

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
    assert response["note"] is None


async def test_find_button_managed_button_no_note(
    hass, setup_integration, mock_coordinator
):
    """Managed button: note is None regardless of translations."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": 5, "device": "aabbccdd", "channel": 0}
    )
    mock_coordinator.resolve_managed_button_fields.return_value = _EMPTY_FIELDS
    response = await hass.services.async_call(
        DOMAIN, "find_button", {}, blocking=True, return_response=True
    )

    assert response["note"] is None


async def test_find_button_unmanaged_button_sets_note(
    hass, setup_integration, mock_coordinator
):
    """Unmanaged button: response contains device/channel and a translated note."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": None, "device": "00019edc", "channel": 0}
    )
    with patch(
        "custom_components.wiser_by_feller.async_get_translations",
        return_value={
            f"component.{DOMAIN}.services.find_button.note_unmanaged_button": "Unmanaged note."
        },
    ):
        response = await hass.services.async_call(
            DOMAIN, "find_button", {}, blocking=True, return_response=True
        )

    assert response["button_id"] is None
    assert response["device"] == "00019edc"
    assert response["channel"] == 0
    assert response["note"] == "Unmanaged note."
    assert response["room_name"] is None
    assert response["device_name"] is None
    assert response["scene_name"] is None


async def test_find_button_unmanaged_falls_back_when_translation_missing(
    hass, setup_integration, mock_coordinator
):
    """Unmanaged button: falls back to the hardcoded English note when translation key absent."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": None, "device": "00019edc", "channel": 0}
    )
    with patch(
        "custom_components.wiser_by_feller.async_get_translations",
        return_value={},
    ):
        response = await hass.services.async_call(
            DOMAIN, "find_button", {}, blocking=True, return_response=True
        )

    assert "unmanaged" in response["note"].lower()


async def test_find_button_creates_notification(
    hass, setup_integration, mock_coordinator
):
    """find_button creates a persistent notification after identifying a button."""
    mock_coordinator.async_find_button = AsyncMock(
        return_value={"button_id": 7, "device": "aabbccdd", "channel": 1}
    )
    mock_coordinator.resolve_managed_button_fields.return_value = _MANAGED_FIELDS
    with patch(
        "custom_components.wiser_by_feller.async_create_notification"
    ) as mock_notify:
        await hass.services.async_call(
            DOMAIN, "find_button", {}, blocking=True, return_response=True
        )

    mock_notify.assert_called_once()
    _, kwargs = mock_notify.call_args
    assert kwargs.get("notification_id") == "wiser_find_button"


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
