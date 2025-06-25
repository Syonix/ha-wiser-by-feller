"""Platform for button integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Device, Hvac, HvacGroup, Load
from aiowiserbyfeller.const import BUTTON_ON, EVENT_CLICK
from aiowiserbyfeller.enum import BlinkPattern
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .climate import WiserHvacGroupDeviceEntity, resolve_room
from .const import HA_BLUE
from .coordinator import WiserCoordinator
from .entity import WiserEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser button entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads.values():
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if not isinstance(load, Hvac):
            # Hvac loads are only supported as part of an HVAC group.
            entities.append(WiserPingEntity(coordinator, load, device, room))

        if await coordinator.async_is_onoff_impulse_load(load):
            entities.append(WiserImpulseEntity(coordinator, load, device, room))
        # else: see light.py

    for device in coordinator.devices.values():
        if len(device.outputs) > 0 or device.id in coordinator.assigned_thermostats:
            continue

        entities.append(WiserPingEntity(coordinator, None, device, None))

    for group in (
        coordinator.hvac_groups.values() if coordinator.hvac_groups is not None else []
    ):
        if group.thermostat_ref is None:
            continue

        thermostat = coordinator.devices[group.thermostat_ref.unprefixed_address]

        if thermostat is None:
            continue

        room = resolve_room(coordinator, group)
        entities.append(WiserClimatePingEntity(coordinator, group, thermostat, room))

    if entities:
        async_add_entities(entities)


class WiserPingEntity(WiserEntity, ButtonEntity):
    """Entity class for ping button entities.

    These allow a load or device to be pinged, resulting in a flashing button
    illumination on the targeted device. This helps to identify devices.
    """

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load | None,
        device: Device,
        room: dict | None,
    ) -> None:
        """Set up wiser ping button entity."""
        super().__init__(coordinator, load, device, room)
        del self._attr_name
        self._attr_unique_id = f"{self._attr_raw_unique_id}_identify"
        self._attr_device_class = ButtonDeviceClass.IDENTIFY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states."""
        return "identify"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

    async def async_press(self, **kwargs: Any) -> None:
        """Ping the load or device to illuminate the button."""
        if self._load:
            await self._load.async_ping(10000, BlinkPattern.RAMP, HA_BLUE)
        else:
            await self.coordinator.async_ping_device(self._device.id)


class WiserClimatePingEntity(WiserHvacGroupDeviceEntity, WiserEntity, ButtonEntity):
    """Entity class for HVAC group ping button entities.

    These allow an HVAC group's assigned thermostat and load channels to be pinged,
    resulting in a flashing button illumination on the targeted device.
    """

    def __init__(
        self,
        coordinator: WiserCoordinator,
        hvac_group: HvacGroup,
        thermostat: Device,
        room: dict | None,
    ) -> None:
        """Set up wiser ping button entity."""
        super().__init__(coordinator, None, None, room)

        self._hvac_group = hvac_group
        self._thermostat = thermostat
        self._attr_device_unique_id = f"{thermostat.id}_hvac_group"
        self._attr_unique_id = f"{thermostat.id}_hvac_group_identify"
        self._attr_device_class = ButtonDeviceClass.IDENTIFY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states."""
        return "identify"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

    async def async_press(self, **kwargs: Any) -> None:
        """Ping the load or device to illuminate the button."""
        for load_id in self._hvac_group.loads:
            await self.coordinator.loads[load_id].async_ping(
                10000, BlinkPattern.RAMP, HA_BLUE
            )

        await self.coordinator.async_ping_device(self._thermostat.id)


class WiserImpulseEntity(WiserEntity, ButtonEntity):
    """Entity class for push button entities.

    These are OnOff loads that have been configured for impulse switching.
    """

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load,
        device: Device,
        room: dict | None,
    ) -> None:
        """Set up wiser impulse button entity."""
        super().__init__(coordinator, load, device, room)

    async def async_press(self, **kwargs: Any) -> None:
        """Simulate a button press of the physical device."""
        await self._load.async_ctrl(BUTTON_ON, EVENT_CLICK)
