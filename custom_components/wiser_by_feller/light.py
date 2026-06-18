"""Platform for light integration."""

from __future__ import annotations

import logging
from typing import Any

from aiowiserbyfeller import DaliRgbw, DaliTw, Device, Dim, Load, OnOff
from aiowiserbyfeller.const import KIND_LIGHT
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBW_COLOR,
    LightEntity,
)
from homeassistant.components.light.const import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    coordinator: WiserCoordinator = entry.runtime_data

    entities = []
    for load in coordinator.loads.values():
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if await coordinator.async_is_onoff_impulse_load(load):
            continue  # See button.py
        if isinstance(load, OnOff) and (load.kind == KIND_LIGHT or load.kind is None):
            entities.append(WiserOnOffEntity(coordinator, load, device, room))
        elif isinstance(load, DaliTw):
            entities.append(WiserDimTwEntity(coordinator, load, device, room))
        elif isinstance(load, DaliRgbw):
            entities.append(WiserDimRgbwEntity(coordinator, load, device, room))
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


class WiserDimTwEntity(WiserEntity, LightEntity):
    """Entity class for DALI tunable white dimmable lights."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 20000

    @property
    def is_on(self) -> bool | None:
        """Return device state."""
        return self._load.raw_state["bri"] > 0

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return wiser_to_brightness(self._load.raw_state["bri"])

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the current color temperature in Kelvin."""
        return self._load.raw_state.get("ct")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on device load with optional brightness and color temperature."""
        bri_kw = kwargs.get(ATTR_BRIGHTNESS)
        ct_kw = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        if bri_kw is not None and ct_kw is not None:
            bri = brightness_to_wiser(bri_kw)
            await self._load.async_set_bri_ct(bri, ct_kw)
            self._load.raw_state["bri"] = bri
            self._load.raw_state["ct"] = ct_kw
        elif ct_kw is not None:
            current_bri = self._load.raw_state.get("bri") or 10000
            await self._load.async_set_bri_ct(current_bri, ct_kw)
            self._load.raw_state["bri"] = current_bri
            self._load.raw_state["ct"] = ct_kw
        elif bri_kw is not None:
            bri = brightness_to_wiser(bri_kw)
            await self._load.async_set_bri(bri)
            self._load.raw_state["bri"] = bri
        else:
            await self._load.async_switch_on()
            self._load.raw_state["bri"] = 100

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off device load."""
        await self._load.async_switch_off()
        self._load.raw_state["bri"] = 0


class WiserDimRgbwEntity(WiserEntity, LightEntity):
    """Entity class for DALI RGBW dimmable lights."""

    _attr_color_mode = ColorMode.RGBW
    _attr_supported_color_modes = {ColorMode.RGBW}

    @property
    def is_on(self) -> bool | None:
        """Return device state."""
        return self._load.raw_state["bri"] > 0

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return wiser_to_brightness(self._load.raw_state["bri"])

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the current RGBW color as a 4-tuple of 0..255 ints."""
        rs = self._load.raw_state
        r, g, b, w = rs.get("red"), rs.get("green"), rs.get("blue"), rs.get("white")
        if r is None or g is None or b is None or w is None:
            return None
        return (r, g, b, w)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on device load with optional brightness and RGBW color."""
        bri_kw = kwargs.get(ATTR_BRIGHTNESS)
        rgbw_kw = kwargs.get(ATTR_RGBW_COLOR)

        if rgbw_kw is not None:
            r, g, b, w = rgbw_kw
            bri = (
                brightness_to_wiser(bri_kw)
                if bri_kw is not None
                else (self._load.raw_state.get("bri") or 10000)
            )
            await self._load.async_set_bri_rgbw(bri, r, g, b, w)
            self._load.raw_state["bri"] = bri
            self._load.raw_state["red"] = r
            self._load.raw_state["green"] = g
            self._load.raw_state["blue"] = b
            self._load.raw_state["white"] = w
        elif bri_kw is not None:
            bri = brightness_to_wiser(bri_kw)
            await self._load.async_set_bri(bri)
            self._load.raw_state["bri"] = bri
        else:
            await self._load.async_switch_on()
            self._load.raw_state["bri"] = 100

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off device load."""
        await self._load.async_switch_off()
        self._load.raw_state["bri"] = 0
