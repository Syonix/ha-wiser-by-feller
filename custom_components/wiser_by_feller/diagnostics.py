"""Diagnostics support for Wiser by Feller integration."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from . import DOMAIN

TO_REDACT = ("token", "serial_nr", "serial_number", "sn", "instance_id", "identifiers")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    loads_json = [load.raw_data for load in coordinator.loads.values()]
    devices_json = [
        coordinator.devices[device_id].raw_data for device_id in coordinator.devices
    ]
    gateway_info_json = coordinator.gateway_info

    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "gateway_info": async_redact_data(gateway_info_json, TO_REDACT),
        "loads": async_redact_data(loads_json, TO_REDACT),
        "rooms": async_redact_data(coordinator.rooms, TO_REDACT),
        "devices": async_redact_data(devices_json, TO_REDACT),
        "scenes": async_redact_data(
            [scene.raw_data for scene in coordinator.scenes.values()], TO_REDACT
        ),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    result: dict[str, Any] = {}
    result["device"] = async_redact_data(json.loads(device.json_repr), TO_REDACT)

    if device.name == f"{entry.title} µGateway":
        result["gateway_info"] = async_redact_data(coordinator.gateway_info, TO_REDACT)
        result["scenes"] = async_redact_data(
            [scene.raw_data for scene in coordinator.scenes.values()], TO_REDACT
        )
    else:
        device_id = next(iter(device.identifiers))[1].partition("_")[0]
        device_data = coordinator.devices[device_id].raw_data
        result["device_data"] = async_redact_data(device_data, TO_REDACT)

    return result
