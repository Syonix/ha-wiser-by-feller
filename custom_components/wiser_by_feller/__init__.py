"""The Wiser by Feller integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Auth, UnsuccessfulRequest, WiserByFellerAPI
from aiowiserbyfeller.enum import BlinkPattern
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.components.light import ATTR_RGB_COLOR
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    CONF_IMPORTUSER,
    DOMAIN,
    IMPORT_USER_UNKNOWN,
    LED_OFF_COLOR,
    MANUFACTURER,
    MIN_FIRMWARE_BUTTON_LED_OVERRIDE,
)
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_STATUS_LIGHT = "status_light"
SERVICE_SET_BUTTON_LED_OVERRIDE = "set_button_led_override"
SERVICE_CLEAR_BUTTON_LED_OVERRIDE = "clear_button_led_override"
SERVICE_FIND_BUTTON = "find_button"

ATTR_BUTTON_ID = "button_id"
ATTR_LED_INDEX = "led_index"
ATTR_EFFECT = "effect"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"


def rgb_tuple_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def validate_rgb_color(value: Any) -> tuple[int, int, int]:
    """Validate RGB color."""
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise vol.Invalid("RGB color must be a list of three integers")

    rgb = tuple(int(color) for color in value)
    if any(color < 0 or color > 255 for color in rgb):
        raise vol.Invalid("RGB values must be between 0 and 255")

    return rgb[0], rgb[1], rgb[2]


SET_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default="0"): vol.In(["0", "1"]),
        vol.Required(ATTR_RGB_COLOR, default=(0, 255, 0)): validate_rgb_color,
        vol.Required(ATTR_EFFECT, default=BlinkPattern.PERMANENT.value): vol.In(
            [pattern.value for pattern in BlinkPattern]
        ),
    }
)

CLEAR_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default="0"): vol.In(["0", "1"]),
    }
)

FIND_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)


def _require_firmware(
    coordinator: WiserCoordinator,
    min_firmware: tuple[int, ...],
) -> None:
    """Raise ServiceValidationError if the gateway firmware is too old."""
    if not coordinator.supports_feature(min_firmware):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="firmware_too_old",
            translation_placeholders={
                "min_version": ".".join(str(x) for x in min_firmware),
                "current_version": (
                    coordinator.gateway_info["sw"]
                    if coordinator.gateway_info
                    else "unknown"
                ),
            },
        )


def _raise_button_led_error(err: UnsuccessfulRequest) -> None:
    """Translate a gateway error from a button LED request into a clear message."""
    if "fw-version too old" in str(err).lower():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_firmware_too_old",
        ) from err
    raise ServiceValidationError(str(err)) from err


def _resolve_coordinator(
    hass: HomeAssistant, entry_id: str | None = None
) -> WiserCoordinator:
    """Resolve the coordinator for a gateway-wide button service.

    Button ids are unique only per µGateway, so the caller selects the gateway
    via its config entry. When exactly one gateway is loaded the selection is
    optional and that gateway is used; with several loaded, one must be chosen.
    """
    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None
    ]

    if entry_id is not None:
        for entry in loaded:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )

    if not loaded:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )
    if len(loaded) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="specify_gateway",
        )
    return loaded[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Wiser by Feller integration.

    All service actions are registered here, once per integration load, so they
    exist even when no config entry is loaded and are never re-registered or
    removed per entry.
    """

    async def handle_status_light(call: ServiceCall) -> None:
        device_id = call.data["device"]
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if device is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == DOMAIN and entry.runtime_data is not None:
                coordinator: WiserCoordinator = entry.runtime_data
                await coordinator.async_set_status_light(call)
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )

    async def async_set_button_led_override(call: ServiceCall) -> None:
        """Set button LED override."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        try:
            await coordinator.api.async_set_button_led(
                button_id=call.data[ATTR_BUTTON_ID],
                led_index=int(call.data[ATTR_LED_INDEX]),
                on=True,
                pattern=BlinkPattern(call.data[ATTR_EFFECT]),
                color=rgb_tuple_to_hex(call.data[ATTR_RGB_COLOR]),
            )
        except UnsuccessfulRequest as err:
            _raise_button_led_error(err)

    async def async_clear_button_led_override(call: ServiceCall) -> None:
        """Clear button LED override."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        try:
            await coordinator.api.async_set_button_led(
                button_id=call.data[ATTR_BUTTON_ID],
                led_index=int(call.data[ATTR_LED_INDEX]),
                on=False,
                pattern=BlinkPattern.PERMANENT,
                color=LED_OFF_COLOR,
            )
        except UnsuccessfulRequest as err:
            _raise_button_led_error(err)

    async def async_find_button_service(call: ServiceCall) -> dict[str, Any]:
        """Find a physical button by activating find-me mode."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        result = await coordinator.async_find_button()

        button_id = result.get("button_id")
        device = result.get("device")
        channel = result.get("channel")

        fields: dict = {"room_name": None, "device_name": None, "scene_name": None}

        if button_id is not None:
            fields = coordinator.resolve_managed_button_fields(button_id)
        elif device is not None:
            # The button exists physically but isn't managed by the gateway, so
            # there is nothing to control. Surface this as a validation error
            # pointing the user to the documentation.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unmanaged_button",
            )

        return {
            "button_id": button_id,
            "device": device,
            "channel": channel,
            "room_name": fields["room_name"],
            "device_name": fields["device_name"],
            "scene_name": fields["scene_name"],
        }

    hass.services.async_register(DOMAIN, SERVICE_STATUS_LIGHT, handle_status_light)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BUTTON_LED_OVERRIDE,
        async_set_button_led_override,
        schema=SET_BUTTON_LED_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_BUTTON_LED_OVERRIDE,
        async_clear_button_led_override,
        schema=CLEAR_BUTTON_LED_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_BUTTON,
        async_find_button_service,
        schema=FIND_BUTTON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiser by Feller from a config entry."""
    # Entries created before the import user was persisted have no record of the
    # user the configuration was copied from. The original choice is not
    # recoverable, so mark it explicitly as unknown rather than guessing a value
    # that would imply false certainty in diagnostics.
    if CONF_IMPORTUSER not in entry.data:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_IMPORTUSER: IMPORT_USER_UNKNOWN},
        )

    session = async_get_clientsession(hass)
    auth = Auth(session, entry.data["host"], token=entry.data["token"])
    api = WiserByFellerAPI(auth)

    wiser_coordinator = WiserCoordinator(
        hass, api, entry.data["host"], entry.data["token"], entry.options
    )
    wiser_coordinator.ws_init()

    entry.runtime_data = wiser_coordinator

    await wiser_coordinator.async_config_entry_first_refresh()
    await async_setup_gateway(hass, entry, wiser_coordinator)
    await async_remove_stale_devices(hass, entry, wiser_coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WiserCoordinator = entry.runtime_data
    await coordinator.ws_close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_stale_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: WiserCoordinator,
) -> None:
    """Remove device registry entries no longer present in the Wiser gateway.

    Only runs when the coordinator holds a complete picture of the loads and
    devices. If the gateway returned partial data (e.g. a transient failure or
    the "Allow missing µGateway data" option), the expected set would be
    incomplete, and we could wrongly delete valid devices together with their
    entities, history and automations. In that case we skip cleanup entirely.
    """
    if coord.loads is None or coord.devices is None:
        _LOGGER.debug("Skipping stale device cleanup: coordinator data is incomplete.")
        return

    device_registry = dr.async_get(hass)

    expected: set[str] = set()

    if coord.gateway is not None:
        expected.add(coord.gateway.combined_serial_number)
    else:
        expected.add(entry.title)

    for load in coord.loads.values():
        expected.add(f"{load.device}_{load.channel}")

    for device in coord.devices.values():
        expected.add(device.id)

    for hvac_group in (coord.hvac_groups or {}).values():
        if hvac_group.thermostat_ref is not None:
            expected.add(f"{hvac_group.thermostat_ref.unprefixed_address}_hvac_group")

    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if any(
            domain == DOMAIN and identifier not in expected
            for domain, identifier in device_entry.identifiers
        ):
            _LOGGER.debug(
                "Detaching stale device %s from config entry", device_entry.name
            )
            # Detach this config entry rather than deleting outright: HA removes
            # the device only if no other config entry still references it.
            device_registry.async_update_device(
                device_entry.id, remove_config_entry_id=entry.entry_id
            )


async def async_setup_gateway(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: WiserCoordinator,
) -> None:
    """Set up the gateway device."""
    assert coord.config_entry is not None
    if coord.gateway is None:
        _LOGGER.warning(
            "The gateway device is not recognized in the coordinator, which can happen if option "
            '"Allow missing µGateway data" is enabled. This leads to non-unique scene identifiers! '
            "Please fix the root cause and disable the option."
        )

        gateway_identifier = coord.config_entry.title
        name = "Unknown µGateway"
        model = None
        sw_version = None
        hw_version = None
    else:
        assert coord.gateway_info is not None
        gateway_identifier = coord.gateway.combined_serial_number
        generation = parse_wiser_device_ref_c(coord.gateway.c["comm_ref"])["generation"]
        name = f"{coord.config_entry.title} µGateway"
        model = coord.gateway.c_name
        sw_version = coord.gateway_info["sw"]
        hw_version = f"{generation} ({coord.gateway.c['comm_ref']})"

    area = None
    for output in coord.gateway.outputs if coord.gateway is not None else []:
        if "load" not in output:
            continue

        if coord.loads is None or coord.rooms is None:
            continue

        load = coord.loads.get(output["load"])
        if load is None:
            continue  # coord.loads only contains loads not marked as unused.

        if load.room is not None and load.room in coord.rooms:
            area = coord.rooms[load.room].get("name")

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        configuration_url=f"http://{coord.api_host}",
        identifiers={(DOMAIN, gateway_identifier)},
        manufacturer=MANUFACTURER,
        model=model,
        name=name,
        sw_version=sw_version,
        hw_version=hw_version,
        suggested_area=area,
    )
