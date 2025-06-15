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
    coordinator: WiserCoordinator,
) -> None:
    """Set up the gateway device."""
    if coordinator.gateway is None:
        _LOGGER.warning(
            "The gateway device is not recognized in the coordinator. This can happen if the "
            '"Allow missing µGateway data" option is set and leads to non-unique scene identifiers. '
            "Please fix the root cause and disable the option."
        )

    gateway = (
        coordinator.gateway.combined_serial_number
        if coordinator.gateway is not None
        else coordinator.config_entry.title
    )
    info = parse_wiser_device_ref_c(coordinator.gateway.c["comm_ref"])

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        configuration_url=f"http://{coordinator.api_host}",
        identifiers={(DOMAIN, gateway)},
        manufacturer=MANUFACTURER,
        model=f"{coordinator.gateway.c_name}",
        name=f"{coordinator.config_entry.title} µGateway",
        sw_version=f"{coordinator.gateway_info['sw']}",
        hw_version=f"{info['generation']} ({coordinator.gateway.c['comm_ref']})",
    )
