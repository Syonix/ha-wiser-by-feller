"""Diagnostics support for Wiser by Feller integration."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .coordinator import WiserCoordinator

TO_REDACT = (
    "token",
    "serial_nr",
    "serial_number",
    "sn",
    "instance_id",
    "identifiers",
    "host",
    "api_host",
)


def _coordinator_meta(coordinator: WiserCoordinator) -> dict[str, Any]:
    """Return coordinator runtime/capability metadata useful for debugging."""
    try:
        websocket_idle = coordinator._ws.is_idle()  # noqa: SLF001
    except Exception:  # noqa: BLE001 - diagnostics must never fail
        websocket_idle = None

    return {
        "last_update_success": coordinator.last_update_success,
        "last_exception": (
            str(coordinator.last_exception) if coordinator.last_exception else None
        ),
        "update_interval_seconds": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        "gateway_api_major_version": coordinator.gateway_api_major_version,
        "is_gen_b": coordinator.is_gen_b,
        "gateway_supports_sensors": coordinator.gateway_supports_sensors,
        "gateway_supports_hvac_groups": coordinator.gateway_supports_hvac_groups,
        "api_host": coordinator.api_host,
        "websocket_idle": websocket_idle,
        "counts": {
            "loads": len(coordinator.loads or {}),
            "devices": len(coordinator.devices or {}),
            "rooms": len(coordinator.rooms or {}),
            "scenes": len(coordinator.scenes or {}),
            "sensors": len(coordinator.sensors or {}),
            "hvac_groups": len(coordinator.hvac_groups or {}),
            "jobs": len(coordinator.jobs or {}),
            "managed_buttons": len(coordinator.managed_buttons or {}),
            "states": len(coordinator.states or {}),
            "system_flags": len(coordinator.system_flags or []),
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: WiserCoordinator = entry.runtime_data

    # Diagnostics should never fail just because some data has not (yet) loaded.
    # Missing sections are emitted as empty rather than raising.
    loads_json = [load.raw_data for load in (coordinator.loads or {}).values()]
    devices_json = [device.raw_data for device in (coordinator.devices or {}).values()]
    gateway_info_json = coordinator.gateway_info

    sensors_json = (
        [sensor.raw_data for sensor in coordinator.sensors.values()]
        if coordinator.sensors
        else []
    )

    managed_buttons_json = [
        button.raw_data for button in (coordinator.managed_buttons or {}).values()
    ]
    hvac_groups_json = [
        group.raw_data for group in (coordinator.hvac_groups or {}).values()
    ]
    jobs_json = [job.raw_data for job in (coordinator.jobs or {}).values()]
    system_flags_json = [flag.raw_data for flag in (coordinator.system_flags or [])]

    # coordinator.states merges load/HVAC live values with the full sensor
    # raw_data (see coordinator.async_update_states). The sensor entries are
    # identical to the dedicated "sensors" section, so drop them here to avoid
    # emitting every sensor twice.
    sensor_ids = set(coordinator.sensors or {})
    states_json = {
        state_id: state
        for state_id, state in (coordinator.states or {}).items()
        if state_id not in sensor_ids
    }

    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "coordinator": async_redact_data(_coordinator_meta(coordinator), TO_REDACT),
        "gateway_info": async_redact_data(gateway_info_json, TO_REDACT),
        "system_health": async_redact_data(coordinator.system_health or {}, TO_REDACT),
        "system_flags": async_redact_data(system_flags_json, TO_REDACT),
        "loads": async_redact_data(loads_json, TO_REDACT),
        "states": async_redact_data(states_json, TO_REDACT),
        "rooms": async_redact_data(coordinator.rooms or {}, TO_REDACT),
        "devices": async_redact_data(devices_json, TO_REDACT),
        "scenes": async_redact_data(
            [scene.raw_data for scene in (coordinator.scenes or {}).values()], TO_REDACT
        ),
        "jobs": async_redact_data(jobs_json, TO_REDACT),
        "sensors": async_redact_data(sensors_json, TO_REDACT),
        "hvac_groups": async_redact_data(hvac_groups_json, TO_REDACT),
        "managed_buttons": async_redact_data(managed_buttons_json, TO_REDACT),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    coordinator: WiserCoordinator = entry.runtime_data
    result: dict[str, Any] = {}
    result["device"] = async_redact_data(
        json.loads(device.json_repr or b"{}"), TO_REDACT
    )

    if device.name == f"{entry.title} µGateway":
        result["coordinator"] = async_redact_data(
            _coordinator_meta(coordinator), TO_REDACT
        )
        result["gateway_info"] = async_redact_data(coordinator.gateway_info, TO_REDACT)
        result["system_health"] = async_redact_data(
            coordinator.system_health or {}, TO_REDACT
        )
        result["system_flags"] = async_redact_data(
            [flag.raw_data for flag in (coordinator.system_flags or [])], TO_REDACT
        )
        result["scenes"] = async_redact_data(
            [scene.raw_data for scene in (coordinator.scenes or {}).values()], TO_REDACT
        )
    else:
        device_id = next(iter(device.identifiers))[1].partition("_")[0]
        wiser_device = (coordinator.devices or {}).get(device_id)
        if wiser_device is not None:
            result["device_data"] = async_redact_data(wiser_device.raw_data, TO_REDACT)
        result["managed_buttons"] = async_redact_data(
            [
                button.raw_data
                for button in (coordinator.managed_buttons or {}).values()
                if button.device == device_id
            ],
            TO_REDACT,
        )

    return result
