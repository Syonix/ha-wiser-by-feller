"""Platform for cover integration."""

from __future__ import annotations

import logging
import asyncio

from aiowiserbyfeller import Device, Load, Motor
from aiowiserbyfeller.const import KIND_AWNING, KIND_VENETIAN_BLINDS

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity
from .util import (
    cover_position_to_wiser,
    cover_tilt_to_wiser,
    wiser_to_cover_position,
    wiser_to_cover_tilt,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser cover entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

        if isinstance(load, Motor) and load.sub_type == "relay":
            entities.append(WiserRelayEntity(coordinator, load, device, room))
        elif isinstance(load, Motor) and load.kind == KIND_VENETIAN_BLINDS:
            entities.append(WiserTiltableCoverEntity(coordinator, load, device, room))
        elif isinstance(load, Motor):
            entities.append(WiserCoverEntity(coordinator, load, device, room))

    if entities:
        async_add_entities(entities)


class WiserRelayEntity(WiserEntity, CoverEntity):
    """Wiser entity class for basic motor entities."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up the relay entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

        # There is no suitable default for "motor", so we use shade.
        self._attr_device_class = CoverDeviceClass.SHADE
        self._tracking_task = None

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed or not."""
        return self._load.state["level"] == 10000

    @property
    def is_moving(self) -> bool:
        """Return if the cover is moving or not."""
        return "moving" in self._load.state and self._load.state["moving"] != "stop"

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return "moving" in self._load.state and self._load.state["moving"] == "up"

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return "moving" in self._load.state and self._load.state["moving"] == "down"

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._load.async_stop()

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._load.async_set_level(0)
        self.start_tracking()

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self._load.async_set_level(10000)
        self.start_tracking()

    def start_tracking(self) -> None:
        """Keep track of cover movement while moving.

        Note: Currently the API does not return an updated position when polled during motion, so
              This whole tracking subroutine is for nothing. However, we'll keep it for now, if a
              future firmware update changes the API behavior.
        """
        if self._tracking_task and not self._tracking_task.done():
            _LOGGER.debug(
                "Load #%s: Stopping previously active tracking task", self._load.id
            )
            self._tracking_task.cancel()

        _LOGGER.debug("Load #%s: Starting tracking task", self._load.id)
        self._tracking_task = asyncio.create_task(self._track_movement_loop())

    async def _track_movement_loop(self) -> None:
        """Keep updating load state while the cover is moving."""
        self._is_tracking = True
        try:
            while True:
                await asyncio.sleep(1)
                _LOGGER.debug("Load #%s: Checking current position", self._load.id)
                await self._load.async_refresh_state()
                if not self.is_moving:
                    return
        except asyncio.CancelledError as e:
            _LOGGER.debug(
                "Load #%s: Checking current position: Tracking task cancelled: %s",
                self._load.id,
                e,
            )
        finally:
            self._is_tracking = False
            _LOGGER.debug("Load #%s: Tracking task stopped", self._load.id)

    async def stop_tracking(self) -> None:
        """Cancel the tracking task if running."""
        if not self._tracking_task:
            _LOGGER.debug("Load #%s: No tracking task running to stop", self._load.id)
            return

        _LOGGER.debug("Load #%s: Stopping tracking task", self._load.id)
        self._tracking_task.cancel()

        try:
            await self._tracking_task
        except asyncio.CancelledError:
            pass

        self._tracking_task = None


class WiserCoverEntity(WiserRelayEntity, CoverEntity):
    """Wiser entity class for non-tiltable covers like shades and awnings."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser cover entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        # There is no suitable default for "motor", so we use shade.
        self._attr_device_class = (
            CoverDeviceClass.AWNING
            if load.kind == KIND_AWNING
            else CoverDeviceClass.SHADE
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover. None is unknown, 0 is closed, 100 is fully open."""
        if self._load.state is None:
            return None

        return wiser_to_cover_position(self._load.state["level"])

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        level = cover_position_to_wiser(kwargs.get(ATTR_POSITION))
        await self._load.async_set_level(level)
        self.start_tracking()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._load.async_stop()


class WiserTiltableCoverEntity(WiserCoverEntity, CoverEntity):
    """Wiser entity class for tiltable covers like venetian blinds."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up Wiser tiltable cover entity."""
        super().__init__(coordinator, load, device, room)

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.STOP_TILT
            | CoverEntityFeature.SET_TILT_POSITION
        )

        self._attr_device_class = CoverDeviceClass.BLIND

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        if (
            self.current_cover_position is None
            or self.current_cover_tilt_position is None
        ):
            return None

        return (
            self.current_cover_position == 0 and self.current_cover_tilt_position == 0
        )

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current position of cover tilt. None is unknown, 0 is closed, 100 is fully open."""
        return wiser_to_cover_tilt(self._load.state["tilt"])

    async def async_open_cover_tilt(self, **kwargs):
        """Open the cover tilt."""
        await self._load.async_set_tilt(9)

    async def async_close_cover_tilt(self, **kwargs):
        """Close the cover tilt."""
        await self._load.async_set_tilt(0)

    async def async_set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        tilt = cover_tilt_to_wiser(kwargs.get(ATTR_TILT_POSITION))
        await self._load.async_set_tilt(tilt)

    async def async_stop_cover_tilt(self, **kwargs):
        """Stop the cover."""
        await self._load.async_stop()
