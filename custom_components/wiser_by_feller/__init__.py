"""The Wiser by Feller integration."""

from __future__ import annotations

import logging

from aiowiserbyfeller import Auth, WiserByFellerAPI
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, MANUFACTURER
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiser by Feller from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    auth = Auth(session, entry.data["host"], token=entry.data["token"])
    api = WiserByFellerAPI(auth)

    wiser_coordinator = WiserCoordinator(
        hass, api, entry.data["host"], entry.data["token"], entry.options
    )
    wiser_coordinator.ws_init()

    hass.data[DOMAIN][entry.entry_id] = wiser_coordinator

    await wiser_coordinator.async_config_entry_first_refresh()
    await async_setup_gateway(hass, entry, wiser_coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.services.async_register(
        DOMAIN, "status_light", wiser_coordinator.async_set_status_light
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

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

        load = coord.loads[output["load"]]
        if load.room is not None and load.room in coord.rooms:
            area = coord.rooms[load.room]["name"]

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
