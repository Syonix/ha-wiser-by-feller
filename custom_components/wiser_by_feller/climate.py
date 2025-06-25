"""Platform for button integration."""

from __future__ import annotations

import logging

from aiowiserbyfeller import Device, HvacGroup
from aiowiserbyfeller.const import UNIT_TEMPERATURE_CELSIUS
from aiowiserbyfeller.hvac import HvacChannelState
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .const import MANUFACTURER
from .coordinator import WiserCoordinator
from .entity import WiserEntity

_LOGGER = logging.getLogger(__name__)


def resolve_room(coordinator: WiserCoordinator, group: HvacGroup) -> dict | None:
    """Return an HVAC group's room.

    If all loads share the same room, return that. Otherwise, return None.
    Unfortunately, the API does not return the sensor's room currently,
    so we can't use that instead.
    """
    rooms = list({coordinator.loads[loadid].room for loadid in group.loads})
    rid = rooms[0] if len(rooms) == 1 else None

    return coordinator.rooms[rid] if rid is not None else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser climate entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for hvac_group in (
        coordinator.hvac_groups.values() if coordinator.hvac_groups is not None else []
    ):
        if hvac_group.thermostat_ref is None:
            continue

        thermostat = coordinator.devices[hvac_group.thermostat_ref.unprefixed_address]

        if thermostat is None:
            continue

        hvac_group.raw_state = coordinator.states[hvac_group.id]
        room = resolve_room(coordinator, hvac_group)
        entities.append(WiserHvacGroupEntity(coordinator, hvac_group, thermostat, room))

    if entities:
        async_add_entities(entities)


class WiserHvacGroupDeviceEntity:
    """Abstract base class for HVAC group entities."""

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""

        if self._hvac_group is None:
            return None

        area = None if self._room is None else self._room["name"]
        via = (
            (DOMAIN, self.coordinator.gateway.combined_serial_number)
            if self.coordinator.gateway is not None
            else None
        )

        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    self._attr_device_unique_id,
                ),
            },
            name=self._hvac_group.name,
            manufacturer=MANUFACTURER,
            model="HVAC Group",
            suggested_area=area,
            via_device=via,
        )


class WiserHvacGroupEntity(WiserHvacGroupDeviceEntity, WiserEntity, ClimateEntity):
    """Entity class for HVAC group entities.

    These represent a combination of a temperature sensor and one or multiple
    heating valve controllers.
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
        self._attr_unique_id = f"{thermostat.id}_hvac_group"  # A temperature sensor can only be bound to one group
        self._attr_device_unique_id = self._attr_unique_id
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
        ]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated entity data from the coordinator."""
        self._hvac_group.raw_state = self.coordinator.states[self._hvac_group.id]
        self.async_write_ha_state()

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes."""
        return [
            HVACMode.OFF,
            HVACMode.COOL if self._hvac_group.flag("cooling") else HVACMode.HEAT,
        ]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation i.e. heat, cool mode."""
        if not self._hvac_group.is_on:
            return HVACMode.OFF
        if self._hvac_group.flag("cooling"):
            return HVACMode.COOL

        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        match self._hvac_group.state:
            case HvacChannelState.COOLING:
                return HVACAction.COOLING
            case HvacChannelState.HEATING:
                return HVACAction.HEATING
            case HvacChannelState.OFF:
                return HVACAction.OFF
            case HvacChannelState.IDLE:
                return HVACAction.IDLE

        return None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._hvac_group.ambient_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._hvac_group.target_temperature

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return 0.5

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._hvac_group.min_temperature

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._hvac_group.max_temperature

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return UNIT_TEMPERATURE_CELSIUS

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        _LOGGER.debug(
            "Turning mode to %s for HVAC group #%s.", hvac_mode, self._hvac_group.id
        )
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:  # HEAT or COOL
            await self.async_turn_on()

    async def async_turn_on(self):
        """Turn the entity on."""
        _LOGGER.debug("Turning on HVAC group #%s.", self._hvac_group.id)
        await self._hvac_group.async_enable()

    async def async_turn_off(self):
        """Turn the entity off."""
        _LOGGER.debug("Turning off HVAC group #%s.", self._hvac_group.id)
        await self._hvac_group.async_disable()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""

        temp = kwargs.get("temperature")
        if kwargs.get("temperature") is None:
            return

        target = round(temp, 1)
        _LOGGER.debug(
            "Setting target temperature for HVAC group #%s to %s °C.",
            self._hvac_group.id,
            target,
        )
        await self._hvac_group.async_set_target_temperature(target)
