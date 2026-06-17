"""Platform for switch integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Device, Load, OnOff, SystemFlag
from aiowiserbyfeller.const import KIND_SWITCH
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser switch entities."""

    coordinator: WiserCoordinator = entry.runtime_data

    assert coordinator.loads is not None
    assert coordinator.states is not None
    assert coordinator.devices is not None
    assert coordinator.rooms is not None

    entities: list = [
        WiserSystemFlag(coordinator, flag) for flag in coordinator.system_flags or []
    ]

    for load in coordinator.loads.values():
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if await coordinator.async_is_onoff_impulse_load(load):
            continue  # See button.py
        if isinstance(load, OnOff) and load.kind == KIND_SWITCH:
            entities.append(WiserOnOffSwitchEntity(coordinator, load, device, room))

    if entities:
        async_add_entities(entities)


class WiserOnOffSwitchEntity(WiserEntity, SwitchEntity):
    """Entity class for simple on/off switches configured as such in the Wiser ecosystem (outlets, fans, etc.)."""

    _load: Load

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load,
        device: Device,
        room: dict | None,
    ) -> None:
        """Set up Wiser on/off switch entity."""
        super().__init__(coordinator, load, device, room)

    @property
    def is_on(self) -> bool | None:
        """Return device state."""
        return self._load.state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on device load."""
        await self._load.async_switch_on()

        # Prevent state showing as on - off - on due to slightly delayed websocket update
        self._load.raw_state["bri"] = 100

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off device load."""
        await self._load.async_switch_off()

        # Prevent state showing as off - on - off due to slightly delayed websocket update
        self._load.raw_state["bri"] = 0


class WiserSystemFlag(CoordinatorEntity["WiserCoordinator"], SwitchEntity):
    """Entity class for system flags in the Wiser ecosystem."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: WiserCoordinator,
        flag: SystemFlag,
    ) -> None:
        """Set up the flag entity."""
        super().__init__(coordinator)

        if coordinator.gateway is None:
            _LOGGER.warning(
                "The gateway device is not recognized in the coordinator. This can happen if the "
                '"Allow missing µGateway data" option is set and leads to non-unique flag identifiers. '
                "Please fix the root cause and disable the option."
            )

        assert coordinator.config_entry is not None
        gateway = (
            coordinator.gateway.combined_serial_number
            if coordinator.gateway is not None
            else coordinator.config_entry.title
        )

        self._attr_unique_id = f"{gateway}_flag_{flag.id}"
        if flag.name is not None:
            self._attr_name = flag.name
        else:
            self._attr_translation_key = "unnamed_flag"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gateway)})
        self._flag = flag

    @property
    def is_on(self) -> bool | None:
        """Return flag state."""
        return self._flag.value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable flag."""
        await self._flag.async_enable()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable flag."""
        await self._flag.async_disable()
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle flag."""
        await self._flag.async_toggle()
        self.async_write_ha_state()
