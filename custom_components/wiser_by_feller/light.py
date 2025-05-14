"""Platform for light integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import (
    DaliRgbw,
    DaliTw,
    Device,
    Dim,
    Load,
    OnOff,
)
from aiowiserbyfeller.const import KIND_LIGHT, KIND_SWITCH

from homeassistant.components.light import ATTR_BRIGHTNESS, LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity
from .util import brightness_to_wiser, wiser_to_brightness

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser light entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if await coordinator.async_is_onoff_impulse_load(load):
            continue  # See button.py
        if isinstance(load, OnOff) and load.kind == KIND_SWITCH:
            entities.append(WiserOnOffSwitchEntity(coordinator, load, device, room))
        elif isinstance(load, OnOff) and (load.kind == KIND_LIGHT or load.kind is None):
            entities.append(WiserOnOffEntity(coordinator, load, device, room))
        elif isinstance(load, DaliTw):
            _LOGGER.warning(
                "Sorry, Dali Tunable White devices are currently not supported. Feel free to request an implementation on GitHub: https://github.com/Syonix/ha-wiser-by-feller/issues/new"
            )
            # entities.append(WiserDimTwEntity(coordinator, load, device, room))
        elif isinstance(load, DaliRgbw):
            _LOGGER.warning(
                "Sorry, Dali RGB devices are currently not supported. Feel free to request an implementation on GitHub: https://github.com/Syonix/ha-wiser-by-feller/issues/new"
            )
            # entities.append(WiserDimRgbEntity(coordinator, load, device, room))
        elif isinstance(load, Dim):  # Includes Dali
            entities.append(WiserDimEntity(coordinator, load, device, room))

    if entities:
        async_add_entities(entities)


class WiserOnOffEntity(WiserEntity, LightEntity):
    """Entity class for simple non-dimmable lights."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser on/off light entity."""
        super().__init__(coordinator, load, device, room)
        self._brightness = None
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_supported_color_modes = [ColorMode.ONOFF]

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


class WiserOnOffSwitchEntity(WiserEntity, SwitchEntity):
    """Entity class for simple non-dimmable switches."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser on/off switch entity."""
        super().__init__(coordinator, load, device, room)
        self._brightness = None

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


class WiserDimEntity(WiserEntity, LightEntity):
    """Entity class for simple dimmable lights."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser dimmable light entity."""
        super().__init__(coordinator, load, device, room)
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = [ColorMode.BRIGHTNESS]

    @property
    def is_on(self) -> bool | None:
        """Return device state."""
        return self._load.raw_state["bri"] > 0

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return wiser_to_brightness(self._load.raw_state["bri"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on device load."""
        if ATTR_BRIGHTNESS in kwargs:
            await self._load.async_set_bri(
                brightness_to_wiser(kwargs.get(ATTR_BRIGHTNESS, 255))
            )
        else:
            await self._load.async_switch_on()

        # Prevent state showing as on - off - on due to slightly delayed websocket update
        self._load.raw_state["bri"] = 100

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off device load."""
        await self._load.async_switch_off()

        # Prevent state showing as off - on - off due to slightly delayed websocket update
        self._load.raw_state["bri"] = 0
