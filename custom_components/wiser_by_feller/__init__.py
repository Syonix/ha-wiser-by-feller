"""The Wiser by Feller integration."""

from __future__ import annotations
from typing import Any

import logging

from aiowiserbyfeller import Auth, WiserByFellerAPI
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiowiserbyfeller.enum import BlinkPattern
from homeassistant.components.light import ATTR_RGB_COLOR
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN, MANUFACTURER
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

SERVICE_SET_BUTTON_LED_OVERRIDE = "set_button_led_override"
SERVICE_CLEAR_BUTTON_LED_OVERRIDE = "clear_button_led_override"

ATTR_BUTTON_ID = "button_id"
ATTR_LED_INDEX = "led_index"
ATTR_EFFECT = "effect"

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

    return rgb


SET_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default=0): cv.positive_int,
        vol.Required(ATTR_RGB_COLOR, default=(0, 255, 0)): validate_rgb_color,
        vol.Required(ATTR_EFFECT, default=BlinkPattern.PERMANENT.value): vol.In(
            [pattern.value for pattern in BlinkPattern]
        ),
    }
)

CLEAR_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default=0): cv.positive_int,
    }
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiser by Feller from a config entry."""
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.services.async_register(
        DOMAIN, "status_light", wiser_coordinator.async_set_status_light
    )

    return True

async def async_set_button_led_override(call: ServiceCall) -> None:
    """Set button LED override."""
    await wiser_coordinator.api.async_set_button_led(
        button_id=call.data[ATTR_BUTTON_ID],
        led_index=call.data[ATTR_LED_INDEX],
        on=True,
        pattern=BlinkPattern(call.data[ATTR_EFFECT]),
        color=rgb_tuple_to_hex(call.data[ATTR_RGB_COLOR]),
    )

async def async_clear_button_led_override(call: ServiceCall) -> None:
    """Clear button LED override."""
    await wiser_coordinator.api.async_set_button_led(
        button_id=call.data[ATTR_BUTTON_ID],
        led_index=call.data[ATTR_LED_INDEX],
        on=False,
        pattern=BlinkPattern.PERMANENT,
        color="#000000",
    )
    
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WiserCoordinator = entry.runtime_data
    await coordinator.ws_close()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.services.async_remove(DOMAIN, "status_light")
        hass.services.async_remove(DOMAIN, SERVICE_SET_BUTTON_LED_OVERRIDE)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_BUTTON_LED_OVERRIDE)

    return unload_ok


async def async_setup_gateway(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: WiserCoordinator,
) -> None:
    """Set up the gateway device."""
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
