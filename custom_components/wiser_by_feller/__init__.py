"""The Wiser by Feller integration."""

from __future__ import annotations

from aiowiserbyfeller import Auth, WiserByFellerAPI
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import WiserCoordinator

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
