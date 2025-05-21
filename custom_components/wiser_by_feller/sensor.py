"""Platform for button integration."""

from __future__ import annotations

import logging

from aiowiserbyfeller import Device, Load, Sensor, Temperature
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser sensor entities."""

    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for load in coordinator.loads:
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None
        info = parse_wiser_device_ref_c(device.c["comm_ref"])
        if info["wlan"]:
            entities.append(WiserRssiEntity(coordinator, load, device, room))

    for sensor in coordinator.sensors.items():
        sensor = sensor[1]
        device = coordinator.devices[sensor.device]
        sensor.raw_data = coordinator.states[sensor.id]
        room = None
        if isinstance(sensor, Temperature):
            entities.append(
                WiserTemperatureSensorEntity(coordinator, None, device, room, sensor)
            )

    if entities:
        async_add_entities(entities)


# TODO: Is this compatible with iot_class local_push?
class WiserRssiEntity(WiserEntity, SensorEntity):
    """A Wiser µGateway RSSI sensor entity."""

    def __init__(
        self, coordinator: WiserCoordinator, load: Load, device: Device, room: dict
    ) -> None:
        """Set up the entity."""
        super().__init__(coordinator, load, device, room)
        self._attr_unique_id = f"{self._load.device}_rssi"
        self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False
        self._rssi = coordinator.rssi

    @property
    def translation_key(self):
        """Return the translation key to translate the entity's name and states."""
        return "rssi"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._rssi = self.coordinator.rssi
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        """Return the RSSI value."""
        return self._rssi


class WiserSensorEntity(WiserEntity, SensorEntity):
    """A Wiser sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load | None,
        device: Device,
        room: dict | None,
        sensor: Sensor,
    ) -> None:
        """Set up the sensor entity."""
        super().__init__(coordinator, load, device, room)
        self._sensor = sensor

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._sensor.raw_data = self.coordinator.states[self._sensor.id]
        self.async_write_ha_state()


class WiserTemperatureSensorEntity(WiserSensorEntity):
    """A Wiser room temperature sensor entity."""

    def __init__(self, coordinator, load, device, room, sensor):
        """Set up the temperature sensor entity."""
        super().__init__(coordinator, load, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        return self._sensor.value_temperature

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of temperature."""
        return UnitOfTemperature.CELSIUS
