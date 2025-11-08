"""Platform for switch integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import SystemFlag
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser switch entities."""

    coordinator: WiserCoordinator = entry.runtime_data
    entities = [
        WiserSystemFlag(coordinator, flag) for flag in coordinator.system_flags or []
    ]

    if entities:
        async_add_entities(entities)


class WiserSystemFlag(CoordinatorEntity, SwitchEntity):
    """Entity class for system flags in the Wiser ecosystem."""

    _attr_has_entity_name = True

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

        gateway = (
            coordinator.gateway.combined_serial_number
            if coordinator.gateway is not None
            else coordinator.config_entry.title
        )

        self._attr_unique_id = f"{gateway}_flag_{flag.id}"
        self._attr_name = flag.name
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
