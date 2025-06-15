"""Platform for scene integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import Scene
from homeassistant.components.scene import Scene as HaScene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser scenes."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for scene in coordinator.scenes.values():
        if scene.job not in coordinator.jobs:
            continue  # Not a Wiser scene

        entities.append(WiserSceneEntity(coordinator, scene))

    if entities:
        async_add_entities(entities)


class WiserSceneEntity(HaScene):
    """Entity class for native scenes in the Wiser ecosystem."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        scene: Scene,
    ) -> None:
        """Set up the scene entity."""
        self.coordinator = coordinator
        self._attr_has_entity_name = True

        if self.coordinator.gateway is None:
            _LOGGER.warning(
                "The gateway device is not recognized in the coordinator. This can happen if the "
                '"Allow missing µGateway data" option is set and leads to non-unique scene identifiers. '
                "Please fix the root cause and disable the option."
            )

        gateway = (
            self.coordinator.gateway.combined_serial_number
            if self.coordinator.gateway is not None
            else coordinator.config_entry.title
        )

        self._attr_unique_id = f"{gateway}_scene_{scene.id}"
        self._attr_name = scene.name
        self._scene = scene

    async def async_activate(self, **kwargs: Any) -> None:
        """Trigger the Wiser scene."""
        job = self.coordinator.jobs[self._scene.job]
        await job.async_trigger_all()
