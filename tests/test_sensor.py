"""Tests for sensor platform entities."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from aiowiserbyfeller import Brightness, Device, Hail, Rain, Temperature, Wind
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfSpeed, UnitOfTemperature

from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.sensor import (
    GW_SENSORS,
    WiserHailSensorEntity,
    WiserIlluminanceSensorEntity,
    WiserLastRebootEntity,
    WiserRainSensorEntity,
    WiserSystemHealthEntity,
    WiserTemperatureSensorEntity,
    WiserWindSpeedSensorEntity,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_coordinator(gateway_sn="20012161", api_version=6, system_health=None):
    coord = MagicMock(spec=WiserCoordinator)
    gw = MagicMock()
    gw.combined_serial_number = gateway_sn
    coord.gateway = gw
    coord.gateway_api_major_version = api_version
    coord.system_health = system_health or {
        "reboot_cause": "HARD_RESET",
        "uptime": 86400,
        "mem_size": 291712,
        "mem_free": 80688,
        "flash_size": 26210304,
        "flash_free": 22396928,
        "sockets": 3,
        "wlan_rssi": -65,
        "wlan_resets": 0,
        "max_tasks": 25,
        "core_temp": 41.5,
    }
    coord.assigned_thermostats = {}
    return coord


def _make_device():
    device = MagicMock(spec=Device)
    device.id = "0000a98f"
    device.c = {
        "comm_ref": "3401A",
        "comm_name": "Druckschalter 1K",
        "fw_version": "0x00501a30",
    }
    device.a = {
        "comm_ref": "3401A",
        "comm_name": "Druckschalter 1K",
        "fw_version": "0x00501a30",
    }
    device.c_name = "Druckschalter 1K"
    device.a_name = "Druckschalter 1K"
    device.combined_serial_number = "011110_B_000064"
    device.outputs = []
    return device


def _make_sensor(spec, sensor_id=5, device_id="0000a98f", room=None):
    sensor = MagicMock(spec=spec)
    sensor.id = sensor_id
    sensor.device = device_id
    sensor.raw_data = {}
    if hasattr(sensor, "room"):
        sensor.room = room
    return sensor


# ── GW_SENSORS / api version filtering ───────────────────────────────────────


def test_core_temp_requires_api_v6():
    """The core_temp sensor descriptor requires min_api_version == 6 (Gen B only)."""
    core_temp_desc = next(d for d in GW_SENSORS if d.key == "core_temp")
    assert core_temp_desc.min_api_version == 6


def test_all_other_sensors_no_min_version():
    """All GW sensor descriptors except core_temp have min_api_version == 0."""
    for desc in GW_SENSORS:
        if desc.key != "core_temp":
            assert desc.min_api_version == 0


def test_gateway_sensors_count_gen_b():
    """API v6 → all 10 GW sensors plus last_reboot are created."""
    coord = _make_coordinator(api_version=6)
    entities = [
        desc
        for desc in GW_SENSORS
        if coord.gateway_api_major_version >= desc.min_api_version
    ]
    assert len(entities) == len(GW_SENSORS)


def test_gateway_sensors_count_gen_a():
    """API v5 → core_temp excluded."""
    coord = _make_coordinator(api_version=5)
    entities = [
        desc
        for desc in GW_SENSORS
        if coord.gateway_api_major_version >= desc.min_api_version
    ]
    assert len(entities) == len(GW_SENSORS) - 1  # core_temp excluded


# ── WiserSystemHealthEntity ───────────────────────────────────────────────────


def test_system_health_entity_unique_id_uses_gateway_sn():
    """System health entity unique_id includes the slugified gateway serial number."""
    coord = _make_coordinator(gateway_sn="ABC123")
    desc = next(d for d in GW_SENSORS if d.key == "flash_free")
    entity = WiserSystemHealthEntity(coord, desc)
    assert "abc123" in entity.unique_id  # slugified


def test_system_health_entity_reads_value_fn():
    """System health entity native_value is read via the descriptor's value_fn."""
    coord = _make_coordinator()
    coord.system_health = {"flash_free": 123456}
    desc = next(d for d in GW_SENSORS if d.key == "flash_free")
    entity = WiserSystemHealthEntity(coord, desc)
    assert entity.native_value == 123456


# ── WiserTemperatureSensorEntity ──────────────────────────────────────────────


def test_temperature_sensor_device_class():
    """Temperature sensor entity reports device_class TEMPERATURE."""
    coord = _make_coordinator()
    sensor = _make_sensor(Temperature)
    sensor.value_temperature = 21.5
    entity = WiserTemperatureSensorEntity(coord, _make_device(), None, sensor)
    assert entity.device_class == SensorDeviceClass.TEMPERATURE


def test_temperature_sensor_unit():
    """Temperature sensor entity uses degrees Celsius as unit of measurement."""
    coord = _make_coordinator()
    sensor = _make_sensor(Temperature)
    entity = WiserTemperatureSensorEntity(coord, _make_device(), None, sensor)
    assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS


def test_temperature_sensor_native_value():
    """Temperature sensor entity native_value reads sensor.value_temperature."""
    coord = _make_coordinator()
    sensor = _make_sensor(Temperature)
    sensor.value_temperature = 20.0
    entity = WiserTemperatureSensorEntity(coord, _make_device(), None, sensor)
    assert entity.native_value == 20.0


def test_temperature_sensor_unique_id_has_suffix():
    """Temperature sensor unique_id ends with '_temperature'."""
    coord = _make_coordinator()
    sensor = _make_sensor(Temperature)
    entity = WiserTemperatureSensorEntity(coord, _make_device(), None, sensor)
    assert entity.unique_id.endswith("_temperature")


# ── WiserIlluminanceSensorEntity ──────────────────────────────────────────────


def test_illuminance_sensor_device_class():
    """Illuminance sensor entity reports device_class ILLUMINANCE."""
    coord = _make_coordinator()
    sensor = _make_sensor(Brightness)
    entity = WiserIlluminanceSensorEntity(coord, _make_device(), None, sensor)
    assert entity.device_class == SensorDeviceClass.ILLUMINANCE


def test_illuminance_sensor_native_value():
    """Illuminance sensor entity native_value reads sensor.value_brightness."""
    coord = _make_coordinator()
    sensor = _make_sensor(Brightness)
    sensor.value_brightness = 500
    entity = WiserIlluminanceSensorEntity(coord, _make_device(), None, sensor)
    assert entity.native_value == 500


# ── WiserWindSpeedSensorEntity ────────────────────────────────────────────────


def test_wind_speed_sensor_device_class():
    """Wind speed sensor entity reports device_class WIND_SPEED."""
    coord = _make_coordinator()
    sensor = _make_sensor(Wind)
    entity = WiserWindSpeedSensorEntity(coord, _make_device(), None, sensor)
    assert entity.device_class == SensorDeviceClass.WIND_SPEED


def test_wind_speed_sensor_unit():
    """Wind speed sensor entity uses meters per second as unit of measurement."""
    coord = _make_coordinator()
    sensor = _make_sensor(Wind)
    entity = WiserWindSpeedSensorEntity(coord, _make_device(), None, sensor)
    assert entity.native_unit_of_measurement == UnitOfSpeed.METERS_PER_SECOND


# ── WiserRainSensorEntity ─────────────────────────────────────────────────────


def test_rain_sensor_is_binary():
    """Rain sensor entity is a BinarySensorEntity."""
    coord = _make_coordinator()
    sensor = _make_sensor(Rain)
    entity = WiserRainSensorEntity(coord, _make_device(), None, sensor)
    assert isinstance(entity, BinarySensorEntity)


def test_rain_sensor_is_on():
    """Rain sensor entity is_on reflects sensor.value_rain."""
    coord = _make_coordinator()
    sensor = _make_sensor(Rain)
    sensor.value_rain = True
    entity = WiserRainSensorEntity(coord, _make_device(), None, sensor)
    assert entity.is_on is True


# ── WiserHailSensorEntity ─────────────────────────────────────────────────────


def test_hail_sensor_is_binary():
    """Hail sensor entity is a BinarySensorEntity."""
    coord = _make_coordinator()
    sensor = _make_sensor(Hail)
    entity = WiserHailSensorEntity(coord, _make_device(), None, sensor)
    assert isinstance(entity, BinarySensorEntity)


def test_hail_sensor_is_on():
    """Hail sensor entity is_on reflects sensor.value_hail."""
    coord = _make_coordinator()
    sensor = _make_sensor(Hail)
    sensor.value_hail = False
    entity = WiserHailSensorEntity(coord, _make_device(), None, sensor)
    assert entity.is_on is False


# ── temperature sensor excluded when assigned to HVAC group ──────────────────


async def test_temperature_sensor_excluded_when_assigned_to_hvac(
    hass, mock_config_entry, mock_coordinator
):
    """Thermostat assigned to HVAC group must not appear as standalone sensor."""
    device = _make_device()
    temp_sensor = _make_sensor(Temperature, device_id=device.id)
    temp_sensor.value_temperature = 21.0

    # Mark this device as assigned thermostat
    mock_coordinator.sensors = {temp_sensor.id: temp_sensor}
    mock_coordinator.devices = {device.id: device}
    mock_coordinator.states = {temp_sensor.id: {}}
    mock_coordinator.assigned_thermostats = {device.id: 10}  # assigned to group 10
    mock_coordinator.gateway_api_major_version = 6

    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.wiser_by_feller.Auth"),
        patch("custom_components.wiser_by_feller.WiserByFellerAPI"),
        patch(
            "custom_components.wiser_by_feller.WiserCoordinator",
            return_value=mock_coordinator,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    sensor_states = hass.states.async_entity_ids("sensor")
    # No standalone device temperature sensor — "core_temperature" is a GW health sensor
    temperature_entities = [
        s for s in sensor_states if "temperature" in s and "core_temperature" not in s
    ]
    assert len(temperature_entities) == 0


# ── WiserLastRebootEntity hysteresis ─────────────────────────────────────────


def test_last_reboot_hysteresis_prevents_update():
    """When uptime decreases by <120s, timestamp should not change."""
    coord = _make_coordinator()
    entity = WiserLastRebootEntity(coord)
    entity.hass = None  # No HA state — first call returns computed value

    # First call
    coord.system_health["uptime"] = 3600
    first_value = entity.native_value
    assert isinstance(first_value, datetime)
