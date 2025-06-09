"""Coordinator for Wiser by Feller integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from types import MappingProxyType
from typing import Any

from aiowiserbyfeller import (
    AuthorizationFailed,
    Device,
    HvacGroup,
    Job,
    Load,
    Scene,
    Sensor,
    UnauthorizedUser,
    UnsuccessfulRequest,
    Websocket,
    WiserByFellerAPI,
)
from aiowiserbyfeller.const import LOAD_SUBTYPE_ONOFF_DTO, LOAD_TYPE_ONOFF
import aiowiserbyfeller.errors
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    GATEWAY_NAME,
    MANUFACTURER,
    OPTIONS_ALLOW_MISSING_GATEWAY_DATA,
)
from .exceptions import (
    InvalidEntityChannelSpecified,
    InvalidEntitySpecified,
    UnexpectedGatewayResult,
)
from .util import rgb_tuple_to_hex

_LOGGER = logging.getLogger(__name__)


def get_unique_id(device: Device, load: Load | None) -> str:
    """Return a unique id for a given device / load combination.

    Note: Update WiserCoordinator.async_update_valid_unique_ids() after changing this!
    """
    return device.id if load is None else f"{load.device}_{load.channel}"


class WiserCoordinator(DataUpdateCoordinator):
    """Class for coordinating all Wiser devices / entities."""

    def __init__(
        self,
        hass,
        api: WiserByFellerAPI,
        host: str,
        token: str,
        options: MappingProxyType[str, Any],
    ) -> None:
        """Initialize global data updater."""
        super().__init__(
            hass,
            _LOGGER,
            name="WiserCoordinator",
            update_interval=timedelta(seconds=30),
        )
        self._hass = hass
        self._api = api
        self._options = options
        self._loads = None
        self._states = None
        self._devices = None
        self._device_ids_by_serial = None
        self._valid_unique_ids = []
        self._scenes = None
        self._sensors = None
        self._system_health = None
        self._hvac_groups = None
        self._assigned_thermostats = {}
        self._jobs = None
        self._rooms = None
        self._gateway = None
        self._gateway_info = None
        self._ws = Websocket(host, token, _LOGGER)

    @property
    def loads(self) -> dict[int, Load] | None:
        """A list of loads of devices configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._loads

    @property
    def states(self) -> dict[int, dict] | None:
        """The current load states of the physical devices."""
        return self._states

    @property
    def devices(self) -> dict[str, Device] | None:
        """A list of devices configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._devices

    @property
    def scenes(self) -> dict[int, Scene] | None:
        """A list of scenes configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._scenes

    @property
    def sensors(self) -> dict[int, Sensor] | None:
        """A list of sensors configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._sensors

    @property
    def hvac_groups(self) -> dict[int, HvacGroup] | None:
        """A list of HVAC groups configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._hvac_groups

    @property
    def assigned_thermostats(self) -> dict[str, int]:
        """A lookup of HVAC groups by assigned thermostat device id."""
        return self._assigned_thermostats

    @property
    def jobs(self) -> dict[int, Job] | None:
        """A list of jobs configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._jobs

    @property
    def gateway(self) -> Device | None:
        """The Wiser device that acts as µGateway in the connected network.

        This should be the only device having WLAN functionality within the same K+ network.
        """
        return self._gateway

    @property
    def gateway_info(self) -> dict | None:
        """A dict debug information of the Wiser device that acts as µGateway in the connected network."""
        return self._gateway_info

    @property
    def rooms(self) -> dict[int, dict] | None:
        """A list of rooms configured in the Wiser by Feller ecosystem (Wiser eSetup app or Wiser Home app)."""
        return self._rooms

    @property
    def system_health(self) -> dict | None:
        """A dict containing system health information of the connected µGateway."""
        return self._system_health

    @property
    def api_host(self) -> str:
        """The API host (IP address)."""
        return self._api.auth.host

    async def async_set_status_light(self, call: ServiceCall) -> bool:
        """Set the button illumination for a channel of a specific device."""

        channel = int(call.data["channel"])
        device_id = call.data["device"]
        registry = dr.async_get(self.hass)
        device = registry.async_get(device_id)
        sn = device.serial_number

        if sn not in self._device_ids_by_serial:
            raise InvalidEntitySpecified(f"Device {device_id} not found!")

        wdevice = self._device_ids_by_serial[sn]

        if channel >= len(self._devices[wdevice].inputs):
            raise InvalidEntityChannelSpecified(
                f"Device {device_id} does not have channel {channel}"
            )

        data = {
            "color": rgb_tuple_to_hex(tuple(call.data["color"])),
            "foreground_bri": call.data["brightness_on"],
            "background_bri": (
                call.data["brightness_off"]
                if "brightness_off" in call.data
                else call.data["brightness_on"]
            ),
        }

        # TODO: Error Handling
        # TODO: It appears the very first time it does not set the configuration
        config = await self._api.async_get_device_config(wdevice)
        await self._api.async_set_device_input_config(config["id"], channel, data)
        await self._api.async_apply_device_config(config["id"])

        return True

    async def async_setup_gateway(self) -> None:
        """Set up the gateway device."""

        info = parse_wiser_device_ref_c(self._gateway.c["comm_ref"])
        self._gateway_info = await self._api.async_get_info_debug()
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            configuration_url=f"http://{self.api_host}",
            identifiers={(DOMAIN, self._gateway.combined_serial_number)},
            manufacturer=MANUFACTURER,
            model=f"{self._gateway.c_name}",
            name=GATEWAY_NAME,
            sw_version=f"{self._gateway_info['sw']}",
            hw_version=f"{info['generation']} ({self._gateway.c['comm_ref']})",
        )

    async def async_ping_device(self, device_id: str) -> bool:
        """Device will light up the yellow LEDs of all buttons for a short time."""
        return await self._api.async_ping_device(device_id)

    async def async_remove_orphan_devices(self, entry: ConfigEntry) -> None:
        """Ensure every device associated with this config entry is still currently present, otherwise remove the device (and thus entities)."""

        registry = dr.async_get(self.hass)

        for device_entry in dr.async_entries_for_config_entry(registry, entry.entry_id):
            for identifier in device_entry.identifiers:
                if identifier[0] == DOMAIN and identifier[1] in self._valid_unique_ids:
                    break
            else:
                registry.async_remove_device(device_entry.id)

    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with asyncio.timeout(10):
                if self._loads is None:
                    await self.async_update_loads()

                if self._rooms is None:
                    await self.async_update_rooms()

                if self._devices is None:
                    await self.async_update_devices()

                if self._jobs is None:
                    await self.async_update_jobs()

                if self._scenes is None:
                    await self.async_update_scenes()

                if self._sensors is None:
                    await self.async_update_sensors()

                if self._hvac_groups is None:
                    await self.async_update_hvac_groups()

                await self.async_update_valid_unique_ids()
                await self.async_update_states()
                await self.async_system_health()
        except AuthorizationFailed as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except UnauthorizedUser as err:
            raise ConfigEntryAuthFailed from err
        except UnsuccessfulRequest as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def ws_init(self) -> None:
        """Set up websocket with µGateway to receive load updates."""
        self._ws.subscribe(self.ws_update_data)
        self._ws.init()
        # TODO: Check connection / reconnect -> Watchdog

    def ws_update_data(self, data: dict) -> None:
        """Process websocket data update."""
        if self._states is None:
            return  # State is not ready yet.

        if "load" in data:
            _LOGGER.debug("Websocket load data update received: %s", data["load"])
            self._states[data["load"]["id"]] = data["load"]["state"]
        elif "sensor" in data:
            _LOGGER.debug("Websocket sensor data update received: %s", data["sensor"])
            self._states[data["sensor"]["id"]] = data["sensor"]
        elif "hvacgroup" in data:
            _LOGGER.debug(
                "Websocket hvacgroup data update received: %s", data["hvacgroup"]
            )
            self._states[data["hvacgroup"]["id"]] = data["hvacgroup"]["state"]
        elif "westgroup" in data:
            # This would probably send updates when Wiser WEST group events happen, e.g. when a cover
            # is retracted due to a wind or rain event. Data updates are handled in the sensor domain
            _LOGGER.debug(
                "Websocket westgroup data update received: %s", data["westgroup"]
            )
        else:
            _LOGGER.debug("Unsupported websocket data update received: %s", data)

        self.async_set_updated_data(None)

    async def async_update_loads(self) -> None:
        """Update Wiser device loads from µGateway."""
        self._loads = {load.id: load for load in await self._api.async_get_used_loads()}

    async def async_update_valid_unique_ids(self) -> None:
        """Update lookup of valid device unique IDs."""
        self._valid_unique_ids = []
        if self.loads is not None:
            for load in self.loads.values():
                self._valid_unique_ids.append(f"{load.device}_{load.channel}")

        if self.devices is not None:
            for device_id in self.devices:
                self._valid_unique_ids.append(device_id)

        if self.hvac_groups is not None:
            for group in self.hvac_groups.values():
                thermostat = self.devices[group.thermostat_ref.unprefixed_address]
                self._valid_unique_ids.append(f"{thermostat.id}_hvac_group")

    async def async_update_devices(self) -> None:
        """Update Wiser devices from µGateway."""
        result = {}
        serials = {}

        for device in await self._api.async_get_devices_detail():
            self.validate_device_data(device)
            result[device.id] = device
            serials[device.combined_serial_number] = device.id

            info = parse_wiser_device_ref_c(device.c["comm_ref"])

            if (
                info["wlan"]
                and self.gateway is not None
                and self.gateway.combined_serial_number != device.combined_serial_number
            ):
                raise UnexpectedGatewayResult(
                    f"Multiple WLAN devices returned: {self.gateway.combined_serial_number} and {device.combined_serial_number}"
                )

            if info["wlan"]:
                self._gateway = device

        self._devices = result
        self._device_ids_by_serial = serials

    def validate_device_data(self, device: Device):
        """Validate API response for critical object keys."""
        if self._options.get(OPTIONS_ALLOW_MISSING_GATEWAY_DATA, False) is True:
            return

        try:
            device.validate_data()
        except aiowiserbyfeller.errors.UnexpectedGatewayResponse as e:
            raise UnexpectedGatewayResult(f"{e}") from e

    async def async_update_rooms(self) -> None:
        """Update Wiser rooms from µGateway."""
        self._rooms = {
            room.get("id"): room for room in await self._api.async_get_rooms()
        }

    async def async_update_states(self) -> None:
        """Update Wiser device states from µGateway."""
        loads = {
            load.get("id"): load.get("state")
            for load in await self._api.async_get_loads_state()
        }
        sensors = {
            sensor.id: sensor.raw_data for sensor in await self._api.async_get_sensors()
        }

        hvac_groups = {
            group["id"]: group["state"]
            for group in await self._api.async_get_hvac_group_states()
        }

        self._states = loads | sensors | hvac_groups

    async def async_update_jobs(self) -> None:
        """Update Wiser jobs from µGateway."""
        self._jobs = {job.id: job for job in await self._api.async_get_jobs()}

    async def async_update_scenes(self) -> None:
        """Update Wiser scenes from µGateway."""
        self._scenes = {scene.id: scene for scene in await self._api.async_get_scenes()}

    async def async_update_sensors(self) -> None:
        """Update Wiser sensors from µGateway."""
        self._sensors = {
            sensor.id: sensor for sensor in await self._api.async_get_sensors()
        }

    async def async_update_hvac_groups(self) -> None:
        """Update Wiser HVAC groups from µGateway."""
        self._hvac_groups = {
            group.id: group for group in await self._api.async_get_hvac_groups()
        }

        self._assigned_thermostats = {}
        for group in self._hvac_groups.values():
            if group.thermostat_ref is None:
                continue

            self._assigned_thermostats[group.thermostat_ref.unprefixed_address] = (
                group.id
            )

    async def async_system_health(self) -> None:
        """Update Wiser system health from µGateway."""
        self._system_health = await self._api.async_get_system_health()

    async def async_is_onoff_impulse_load(self, load: Load) -> bool:
        """Check if on/off load is of subtype impulse.

        Note: Impulse and Minuterie (delayed off) are both of the subtype "dto". The only difference is,
              that the Impulse delay ranges from 100ms to 1s and the Minuterie delay from 10s to 30min.
        """
        if load.type != LOAD_TYPE_ONOFF or load.sub_type != LOAD_SUBTYPE_ONOFF_DTO:
            return False

        config = await self._api.async_get_device_config(load.device)
        delay = config["outputs"][load.channel]["delay_ms"]

        return delay < 10000
