"""Platform for button integration."""

from __future__ import annotations

import datetime as dt
import logging

from aiowiserbyfeller import (
    Brightness,
    Device,
    Hail,
    Load,
    Rain,
    Sensor,
    Temperature,
    Wind,
)
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfInformation,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from slugify import slugify

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
    for load in coordinator.loads.values():
        load.raw_state = coordinator.states[load.id]
        device = coordinator.devices[load.device]
        room = coordinator.rooms[load.room] if load.room is not None else None

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

    gateway_serial = coordinator.gateway.combined_serial_number
    gateway_sensor_map = {
        "uptime": (WiserUptimeSensorEntity, int, "Uptime", False),
        "flash_free": (WiserDataSensorEntity, int, "Flash Free", True),
        "flash_size": (WiserDataSensorEntity, int, "Flash Size", False),
        "mem_size": (WiserDataSensorEntity, int, "Mem Size", False),
        "mem_free": (WiserDataSensorEntity, int, "Mem Free", True),
        "core_temp": (WiserCoreTempSensorEntity, float, "Core Temperature", True),
        "wlan_resets": (WiserWlanResetsSensorEntity, int, "WLAN Resets", True),
        "max_tasks": (WiserMaxTasksSensorEntity, int, "Max Tasks", False),
        "wlan_rssi": (WiserWlanRSSISensorEntity, int, "WLAN RSSI", False),
        "reboot_cause": (WiserRebootCauseTextEntity, str, "Reboot Cause", True),
        "sockets": (WiserSocketsSensorEntity, int, "Sockets", False),
    }

    for key, value in coordinator.system_health.items():
        entity_class, value_type, entity_name, enabled = gateway_sensor_map.get(
            key, (None, None, None)
        )
        if entity_class:
            entities.append(
                entity_class(
                    coordinator,
                    gateway_serial,
                    entity_name,
                    value_type(value),
                    key,
                    enabled,
                )
            )

    if entities:
        async_add_entities(entities)


# TODO: Is this compatible with iot_class local_push?
class WiserSystemHealthEntity(CoordinatorEntity):
    """A Wiser µGateway sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: float,
        key: str,
        enabled: bool = True,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator),)
        self._slugify_gateway_serial = slugify(gateway_serial, separator="_")
        self._key = key
        self.coordinator_context = f"{self._slugify_gateway_serial}_{self._key}"
        self._attr_raw_unique_id = f"{self._slugify_gateway_serial}"
        self._attr_unique_id = f"{self._attr_raw_unique_id}_{self._key}"
        self._attr_name = name
        self._attr_translation_key = self._key
        self._attr_has_entity_name = True
        self._attr_device_class = None
        self._attr_entity_category = None
        self._attr_entity_registry_enabled_default = enabled
        self.device_info = DeviceInfo(identifiers={(DOMAIN, gateway_serial)})
        self._value = value

    @property
    def native_value(self) -> int | float | str | None:
        """Return the value."""
        return self._value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        self._value = self.coordinator.system_health.get(self._key, self._value)


class WiserUptimeSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Uptime sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:clock-start"

    @property
    def native_value(self) -> int | None:
        """Return the Uptime value."""
        self.offset = dt.timedelta(seconds=self._value)
        self._date_since_boot = dt_util.utcnow() - self.offset


class WiserDataSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Data sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorDeviceClass.DATA_SIZE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
        self._attr_suggested_unit_of_measurement = UnitOfInformation.KIBIBYTES
        self._attr_suggested_display_precision = 0


class WiserCoreTempSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Core Temperature sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: float,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_suggested_display_precision = 1


class WiserWlanResetsSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Wlan Resets sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:wifi-alert"


class WiserMaxTasksSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Max Tasks sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:list-box-outline"


class WiserWlanRSSISensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway WLAN RSSI sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT


class WiserSocketsSensorEntity(WiserSystemHealthEntity, SensorEntity):
    """A Wiser µGateway Sockets sensor entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: int,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_device_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:arrow-expand-horizontal"


class WiserRebootCauseTextEntity(WiserSystemHealthEntity, TextEntity):
    """A Wiser µGateway Reboot Cause text entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        gateway_serial: str,
        name: str,
        value: str,
        key: str,
        enabled: bool,
    ) -> None:
        """Set up the entity."""
        (super().__init__(coordinator, gateway_serial, name, value, key, enabled),)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:restart-alert"


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
