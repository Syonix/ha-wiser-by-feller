"""Platform for sensor integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging

from aiowiserbyfeller import Brightness, Device, Hail, Rain, Sensor, Temperature, Wind
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    STATE_UNAVAILABLE,
    EntityCategory,
    UnitOfInformation,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from slugify import slugify

from . import DOMAIN
from .coordinator import WiserCoordinator
from .entity import WiserEntity

_LOGGER = logging.getLogger(__name__)
RESTART_DELTA_THRESHOLD = 120


@dataclass(frozen=True, kw_only=True)
class GatewaySensorEntityDescription(SensorEntityDescription):
    """Describes a Wiser µGateway system health sensor entity."""

    value_fn: Callable[[dict], datetime | StateType]


GW_SENSORS: tuple[GatewaySensorEntityDescription, ...] = (
    GatewaySensorEntityDescription(
        key="flash_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        suggested_display_precision=0,
        value_fn=lambda data: data["flash_free"],
    ),
    GatewaySensorEntityDescription(
        key="flash_size",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        suggested_display_precision=0,
        value_fn=lambda data: data["flash_size"],
    ),
    GatewaySensorEntityDescription(
        key="mem_size",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        suggested_display_precision=0,
        value_fn=lambda data: data["mem_size"],
    ),
    GatewaySensorEntityDescription(
        key="mem_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        suggested_display_precision=0,
        value_fn=lambda data: data["mem_free"],
    ),
    GatewaySensorEntityDescription(
        key="core_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda data: data["core_temp"],
    ),
    GatewaySensorEntityDescription(
        key="wlan_resets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:wifi-alert",
        value_fn=lambda data: data["wlan_resets"],
    ),
    GatewaySensorEntityDescription(
        key="max_tasks",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:list-box-outline",
        value_fn=lambda data: data["max_tasks"],
    ),
    GatewaySensorEntityDescription(
        key="wlan_rssi",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=lambda data: data["wlan_rssi"],
    ),
    GatewaySensorEntityDescription(
        key="reboot_cause",
        icon="mdi:restart-alert",
        value_fn=lambda data: data["reboot_cause"],
    ),
    GatewaySensorEntityDescription(
        key="sockets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-expand-horizontal",
        value_fn=lambda data: data["sockets"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wiser sensor entities."""

    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        WiserSystemHealthEntity(coordinator, description) for description in GW_SENSORS
    ]

    entities.append(WiserLastRebootEntity(coordinator))

    for sensor in coordinator.sensors.values():
        device = coordinator.devices[sensor.device]
        sensor.raw_data = coordinator.states[sensor.id]

        # Currently sensors do not return a room id, even though in the Wiser system they
        # are assigned to one. In some implementations it returns a room name. This
        # implementation can handle all cases.
        if hasattr(sensor, "room") and isinstance(sensor.room, int):
            room = coordinator.rooms[sensor.room]
        elif hasattr(sensor, "room") and isinstance(sensor.room, str):
            room = {"name": sensor.room}
        else:
            room = None

        if (
            isinstance(sensor, Temperature)
            and sensor.device not in coordinator.assigned_thermostats
        ):
            # We don't want to show a thermostat as a standalone sensor if it is
            # assigned to an HVAC group. See climate.py for that.
            entities.append(
                WiserTemperatureSensorEntity(coordinator, device, room, sensor)
            )
        elif isinstance(sensor, Brightness):
            entities.append(
                WiserIlluminanceSensorEntity(coordinator, device, room, sensor)
            )
        elif isinstance(sensor, Wind):
            entities.append(
                WiserWindSpeedSensorEntity(coordinator, device, room, sensor)
            )
        elif isinstance(sensor, Rain):
            entities.append(WiserRainSensorEntity(coordinator, device, room, sensor))
        elif isinstance(sensor, Hail):
            entities.append(WiserHailSensorEntity(coordinator, device, room, sensor))

    if entities:
        async_add_entities(entities)


# TODO: Is this compatible with iot_class local_push?
class WiserSystemHealthEntity(CoordinatorEntity, SensorEntity):
    """A Wiser µGateway system health sensor entity."""

    entity_description: GatewaySensorEntityDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WiserCoordinator,
        entity_description: GatewaySensorEntityDescription,
    ) -> None:
        """Set up the entity."""
        super().__init__(coordinator, entity_description)
        self.gateway = coordinator.gateway.combined_serial_number
        slugify_gateway = slugify(f"{self.gateway}", separator="_")
        self.entity_description = entity_description
        self._attr_translation_key = entity_description.key
        self._attr_unique_id = f"{slugify_gateway}_{entity_description.key}"

        self.coordinator_context = f"{slugify_gateway}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self.gateway)})
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.system_health
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.system_health
        )


class WiserLastRebootEntity(CoordinatorEntity, SensorEntity):
    """A Wiser µGateway system health sensor entity to return the last reboot."""

    def __init__(self, coordinator: WiserCoordinator) -> None:
        """Set up the entity."""
        super().__init__(coordinator)
        self.gateway = coordinator.gateway.combined_serial_number
        slugify_gateway = slugify(f"{self.gateway}", separator="_")
        self._attr_translation_key = "last_reboot"
        self._attr_unique_id = self.coordinator_context = (
            f"{slugify_gateway}_last_reboot"
        )
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self.gateway)})
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:clock-start"

    @property
    def native_value(self) -> datetime:
        """Return the value reported by the sensor.

        The API returns seconds since reboot. If we ingest that in HA, we have a state change each second,
        which is not ideal. Therefore, we calculate the timestamp of the last reboot. We return the new value only,
        if it differs more than the configured threshold.
        """
        new_value = dt_util.utcnow() - dt_util.dt.timedelta(
            seconds=self.coordinator.system_health["uptime"]
        )

        if self.hass:
            current = self.hass.states.get(self.entity_id)
            if current and current.state not in (None, STATE_UNAVAILABLE):
                try:
                    current_value = datetime.fromisoformat(current.state)
                    if (
                        abs((current_value - new_value).total_seconds())
                        < RESTART_DELTA_THRESHOLD
                    ):
                        return current_value
                except (ValueError, TypeError):
                    pass

        return new_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()


class WiserSensorEntity(WiserEntity):
    """A Wiser sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        device: Device,
        room: dict | None,
        sensor: Sensor,
    ) -> None:
        """Set up the sensor entity."""
        super().__init__(coordinator, None, device, room)
        del self._attr_name
        self._sensor = sensor

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._sensor.raw_data = self.coordinator.states[self._sensor.id]
        self.async_write_ha_state()


class WiserTemperatureSensorEntity(WiserSensorEntity, SensorEntity):
    """A Wiser room temperature sensor entity."""

    def __init__(self, coordinator, device, room, sensor: Temperature):
        """Set up the temperature sensor entity."""
        super().__init__(coordinator, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        return self._sensor.value_temperature

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of temperature."""
        return UnitOfTemperature.CELSIUS


class WiserIlluminanceSensorEntity(WiserSensorEntity, SensorEntity):
    """A Wiser illuminance sensor entity."""

    def __init__(self, coordinator, device, room, sensor: Brightness):
        """Set up the illuminance sensor entity."""
        super().__init__(coordinator, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_illuminance"
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return the current illuminance."""
        return self._sensor.value_brightness

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of illuminance."""
        return LIGHT_LUX


class WiserWindSpeedSensorEntity(WiserSensorEntity, SensorEntity):
    """A Wiser wind speed sensor entity."""

    def __init__(self, coordinator, device, room, sensor: Wind):
        """Set up the wind speed sensor entity."""
        super().__init__(coordinator, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_wind_speed"
        self._attr_device_class = SensorDeviceClass.WIND_SPEED
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> int | None:
        """Return the current wind speed."""
        return self._sensor.value_wind_speed

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of wind speed."""
        return UnitOfSpeed.METERS_PER_SECOND


class WiserRainSensorEntity(WiserSensorEntity, BinarySensorEntity):
    """A Wiser rain sensor entity."""

    def __init__(self, coordinator, device, room, sensor: Rain):
        """Set up the rain sensor entity."""
        super().__init__(coordinator, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_rain"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_translation_key = "rain"
        self._attr_icon = "mdi:weather-rainy"

    @property
    def is_on(self) -> bool | None:
        """Return the current rain state."""
        return self._sensor.value_rain


class WiserHailSensorEntity(WiserSensorEntity, BinarySensorEntity):
    """A Wiser hail sensor entity."""

    def __init__(self, coordinator, device, room, sensor: Hail):
        """Set up the hail sensor entity."""
        super().__init__(coordinator, device, room, sensor)
        self._attr_unique_id = f"{self._attr_raw_unique_id}_hail"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_translation_key = "hail"
        self._attr_icon = "mdi:weather-hail"

    @property
    def is_on(self) -> bool | None:
        """Return the current hail state."""
        return self._sensor.value_hail
