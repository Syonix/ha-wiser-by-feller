"""Coordinator for Wiser by Feller integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from types import MappingProxyType
from typing import Any

from aiowiserbyfeller import (
    AuthorizationFailed,
    Button,
    Device,
    HvacGroup,
    Job,
    Load,
    Scene,
    Sensor,
    SystemFlag,
    UnauthorizedUser,
    UnsuccessfulRequest,
    Websocket,
    WiserByFellerAPI,
)
from aiowiserbyfeller.const import LOAD_SUBTYPE_ONOFF_DTO, LOAD_TYPE_ONOFF
from aiowiserbyfeller.enum import BlinkPattern
import aiowiserbyfeller.errors
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    EVENT_BUTTON,
    HA_BLUE,
    LED_OFF_COLOR,
    OPTIONS_ALLOW_MISSING_GATEWAY_DATA,
)
from .exceptions import UnexpectedGatewayResult
from .util import resolve_device_name, rgb_tuple_to_hex

_LOGGER = logging.getLogger(__name__)


def get_unique_id(device: Device, load: Load | None) -> str:
    """Return a unique id for a given device / load combination."""
    return device.id if load is None else f"{load.device}_{load.channel}"


class WiserCoordinator(DataUpdateCoordinator[None]):
    """Class for coordinating all Wiser devices / entities."""

    def __init__(
        self,
        hass: Any,
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
        self._loads: dict[int, Any] | None = None
        self._states: dict[int, Any] | None = None
        self._devices: dict[str, Any] | None = None
        self._device_ids_by_serial: dict[str, str] | None = None
        self._scenes: dict[int, Any] | None = None
        self._sensors: dict[int, Any] | None = None
        self._system_flags: list[Any] | None = None
        self._system_health: dict[str, Any] | None = None
        self._hvac_groups: dict[int, Any] | None = None
        self._assigned_thermostats: dict[str, int] = {}
        self._jobs: dict[int, Any] | None = None
        self._rooms: dict[int, Any] | None = None
        self._gateway: Any = None
        self._gateway_info: dict[str, Any] | None = None
        self._managed_buttons: dict[int, Any] | None = None
        self._findme_button_future: asyncio.Future | None = None
        self._ws = Websocket(host, token, _LOGGER)
        self._ws_was_idle = False

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
    def system_flags(self) -> list[SystemFlag] | None:
        """A list of system flags of the connected µGateway."""
        return self._system_flags

    @property
    def managed_buttons(self) -> dict[int, Button] | None:
        """A dict of managed (registered) buttons, keyed by button ID."""
        return self._managed_buttons

    @property
    def api_host(self) -> str:
        """The API host (IP address)."""
        return self._api.auth.host

    @property
    def gateway_api_major_version(self) -> int | None:
        """Gateway major version (e.g. 5 for generation A devices)."""
        return (
            int(self.gateway_info["api"][:1]) if self.gateway_info is not None else None
        )

    @property
    def is_gen_b(self) -> bool:
        """State if the µGateway is a generation B device (Starting from API version 6)."""
        version = self.gateway_api_major_version

        return version is not None and version >= 6

    @property
    def gateway_supports_sensors(self) -> bool:
        """State if the µGateway supports sensor devices (Gen B)."""
        return self.is_gen_b

    @property
    def gateway_supports_hvac_groups(self) -> bool:
        """State if the µGateway supports HVAC groups (Gen B)."""
        return self.is_gen_b

    @property
    def api(self) -> WiserByFellerAPI:
        """Wiser by Feller API."""
        return self._api

    async def async_set_status_light(self, call: ServiceCall) -> None:
        """Set the button illumination for a channel of a specific device."""
        channel = int(call.data["channel"])
        device_id = call.data["device"]
        registry = dr.async_get(self.hass)
        device = registry.async_get(device_id)
        if (
            device is None
            or self._device_ids_by_serial is None
            or self._devices is None
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        sn = device.serial_number

        if sn not in self._device_ids_by_serial:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )

        wdevice = self._device_ids_by_serial[sn]

        if channel >= len(self._devices[wdevice].inputs):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_channel",
                translation_placeholders={"channel": str(channel)},
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

        try:
            config = await self._api.async_get_device_config(wdevice)
            await self._api.async_set_device_input_config(config["id"], channel, data)
            await self._api.async_apply_device_config(config["id"])
        except UnsuccessfulRequest as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="status_light_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_ping_device(self, device_id: str) -> bool:
        """Device will light up the yellow LEDs of all buttons for a short time."""
        return await self._api.async_ping_device(device_id)

    async def async_update_managed_buttons(self) -> None:
        """Update managed buttons from µGateway."""
        _LOGGER.debug("Attempting to update managed buttons from µGateway...")
        buttons = await self._api.async_get_managed_buttons()
        self._managed_buttons = {btn.id: btn for btn in buttons if btn.id is not None}

    async def async_find_button(self) -> dict:
        """Activate find-me mode and wait for a physical button press."""
        if (
            self._findme_button_future is not None
            and not self._findme_button_future.done()
        ):
            raise ServiceValidationError("Find button operation already in progress")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._findme_button_future = future

        try:
            await self._api.async_find_buttons(
                on=True,
                time=2,
                blink_pattern=BlinkPattern.RAMP,
                color=HA_BLUE,
            )
            result = await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError as err:
            raise ServiceValidationError(
                "No button was pressed within 2 minutes. Find-me mode cancelled."
            ) from err
        finally:
            self._findme_button_future = None
            await self._api.async_find_buttons(
                on=False, time=0, blink_pattern=BlinkPattern.RAMP, color=LED_OFF_COLOR
            )

        if isinstance(result, int):
            button = (
                self._managed_buttons.get(result) if self._managed_buttons else None
            )
            return {
                "button_id": result,
                "device": button.device if button else None,
                "channel": button.channel if button else None,
            }

        if isinstance(result, dict):
            return {
                "button_id": None,
                "device": result.get("device"),
                "channel": result.get("channel"),
            }

        return {"button_id": None, "device": None, "channel": None}

    def resolve_managed_button_fields(self, button_id: int) -> dict:
        """Return structured display fields for a managed button."""
        empty: dict = {"room_name": None, "device_name": None, "scene_name": None}

        if self._managed_buttons is None or self._devices is None:
            return empty

        button = self._managed_buttons.get(button_id)
        if button is None:
            return empty

        device = self._devices.get(button.device)
        if device is None:
            return empty

        room_name = None
        for output in device.outputs:
            load_id = output.get("load")
            if load_id is None or self._loads is None:
                continue
            load = self._loads.get(load_id)
            if load is None:
                continue
            if (
                load.room is not None
                and self._rooms is not None
                and load.room in self._rooms
            ):
                room_name = self._rooms[load.room]["name"]
                break

        device_name = resolve_device_name(device, None, None)

        scene_name = None
        job_id = button.raw_data.get("job")
        if job_id is not None and self._scenes is not None:
            for scene in self._scenes.values():
                if scene.job == job_id:
                    scene_name = scene.name
                    break

        return {
            "room_name": room_name,
            "device_name": device_name,
            "scene_name": scene_name,
        }

    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            _LOGGER.debug("Attempting to update data from µGateway...")
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with asyncio.timeout(10):
                await self.async_update_gateway_info()

            if self._loads is None:
                async with asyncio.timeout(10):
                    await self.async_update_loads()

            if self._rooms is None:
                async with asyncio.timeout(10):
                    await self.async_update_rooms()

            if self._devices is None:
                # Updating the detailed device information takes ~1 second per device on µGWv1
                # and the limit for a µGWv1 system is at 50 devices. µGWv2 devices allow for
                # 100 devices, but update much faster (~500 ms for 30 devices).
                async with asyncio.timeout(75):
                    await self.async_update_devices()

            if self._jobs is None:
                async with asyncio.timeout(10):
                    await self.async_update_jobs()

            if self._scenes is None:
                async with asyncio.timeout(10):
                    await self.async_update_scenes()

            if self._system_flags is None:
                async with asyncio.timeout(10):
                    await self.async_update_system_flags()

            if self._sensors is None and self.gateway_supports_sensors:
                async with asyncio.timeout(10):
                    await self.async_update_sensors()

            if self._hvac_groups is None and self.gateway_supports_hvac_groups:
                async with asyncio.timeout(10):
                    await self.async_update_hvac_groups()

            if self._managed_buttons is None:
                try:
                    async with asyncio.timeout(10):
                        await self.async_update_managed_buttons()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Failed to load managed buttons, find_button service will not resolve labels. Fix this by updating your µGateway. (Error: %s)",
                        err,
                    )
                    self._managed_buttons = {}

            async with asyncio.timeout(10):
                await self.async_update_states()

            async with asyncio.timeout(10):
                await self.async_update_system_health()

            _LOGGER.debug("Successfully updated data from µGateway.")

            # Reconnect WebSocket if it has died
            if self._ws.is_idle():
                if not self._ws_was_idle:
                    _LOGGER.warning(
                        "WebSocket connection to µGateway is idle/disconnected. Reconnecting..."
                    )
                    self._ws_was_idle = True
                await self.ws_close()
                self._ws.reset_error_count()
                self._ws.init()
            elif self._ws_was_idle:
                _LOGGER.info("WebSocket connection to µGateway re-established.")
                self._ws_was_idle = False

        except asyncio.TimeoutError as err:
            raise UpdateFailed("Timeout while fetching data from µGateway") from err
        except (AuthorizationFailed, UnauthorizedUser) as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except UnsuccessfulRequest as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def ws_close(self) -> None:
        """Close the WebSocket connection if it exists."""
        await self._ws.async_close()

    def ws_init(self) -> None:
        """Set up websocket with µGateway to receive load updates."""
        self._ws.subscribe(self.ws_update_data)
        self._ws.init()
        # WebSocket reconnection is handled in _async_update_data()

    def ws_update_data(self, data: dict) -> None:
        """Process websocket data update."""
        if self._states is None:
            return  # State is not ready yet.

        if "findme" in data:
            if "button" in data["findme"]:
                _LOGGER.debug(
                    "Websocket findme button event received: %s", data["findme"]
                )
                if self._findme_button_future and not self._findme_button_future.done():
                    self._findme_button_future.set_result(data["findme"]["button"])
            return  # findme events don't update entity state

        if "load" in data:
            _LOGGER.debug("Websocket load data update received: %s", data["load"])
            self._states[data["load"]["id"]] = data["load"]["state"]
        elif "sensor" in data:
            _LOGGER.debug("Websocket sensor data update received: %s", data["sensor"])
            sid = data["sensor"]["id"]
            # The WebSocket payload is partial (only id + value). Merge into the
            # existing full raw_data so type/device/unit fields are preserved.
            if sid in self._states and isinstance(self._states[sid], dict):
                self._states[sid] = {**self._states[sid], **data["sensor"]}
            else:
                self._states[sid] = data["sensor"]
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
        elif "button" in data:
            # Physical button presses. These don't mutate load state, they're fired on the HA bus for
            # device triggers and raw event automations to consume.
            btn = data["button"]
            _LOGGER.debug("Websocket button event received: %s", btn)
            if self.config_entry is not None:
                self.hass.bus.async_fire(
                    EVENT_BUTTON,
                    {
                        "config_entry_id": self.config_entry.entry_id,
                        "button_id": btn["id"],
                        "event": btn["cmd"]["event"],
                        "type": btn["cmd"].get("type"),
                    },
                )
            return  # button events don't update entity state
        else:
            _LOGGER.debug("Unsupported websocket data update received: %s", data)

        self.async_set_updated_data(None)

    async def async_update_loads(self) -> None:
        """Update Wiser device loads from µGateway."""
        _LOGGER.debug("Attempting to update device loads from µGateway...")
        loads = await self._api.async_get_used_loads()
        self._loads = {load.id: load for load in loads}
        self._sync_unknown_type_issues(loads, "load", extra_log_attrs=["sub_type"])

    async def async_update_devices(self) -> None:
        """Update Wiser devices from µGateway."""
        result = {}
        serials = {}

        _LOGGER.debug(
            "Attempting to update detailed device information from µGateway..."
        )
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
                    translation_domain=DOMAIN,
                    translation_key="multiple_wlan_devices",
                    translation_placeholders={
                        "first": self.gateway.combined_serial_number,
                        "second": device.combined_serial_number,
                    },
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
            raise UnexpectedGatewayResult(
                translation_domain=DOMAIN,
                translation_key="unexpected_gateway_result",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_update_rooms(self) -> None:
        """Update Wiser rooms from µGateway."""
        _LOGGER.debug("Attempting to update rooms from µGateway...")
        self._rooms = {
            room.get("id"): room for room in await self._api.async_get_rooms()
        }

    async def async_update_states(self) -> None:
        """Update Wiser device states from µGateway."""
        loads = {
            load.get("id"): load.get("state")
            for load in await self._api.async_get_loads_state()
        }
        sensors = (
            {
                sensor.id: sensor.raw_data
                for sensor in await self._api.async_get_sensors()
            }
            if self.gateway_supports_sensors
            else {}
        )

        hvac_groups = (
            {
                group["id"]: group["state"]
                for group in await self._api.async_get_hvac_group_states()
            }
            if self.gateway_supports_hvac_groups
            else {}
        )

        self._states = loads | sensors | hvac_groups

    async def async_update_jobs(self) -> None:
        """Update Wiser jobs from µGateway."""
        _LOGGER.debug("Attempting to update jobs from µGateway...")
        self._jobs = {job.id: job for job in await self._api.async_get_jobs()}

    async def async_update_scenes(self) -> None:
        """Update Wiser scenes from µGateway."""
        _LOGGER.debug("Attempting to update scenes from µGateway...")
        self._scenes = {scene.id: scene for scene in await self._api.async_get_scenes()}

    async def async_update_sensors(self) -> None:
        """Update Wiser sensors from µGateway."""
        _LOGGER.debug("Attempting to update sensors from µGateway...")
        sensors = await self._api.async_get_sensors()
        self._sensors = {sensor.id: sensor for sensor in sensors}
        self._sync_unknown_type_issues(sensors, "sensor")

    async def async_update_hvac_groups(self) -> None:
        """Update Wiser HVAC groups from µGateway."""
        _LOGGER.debug("Attempting to update HVAC groups from µGateway...")
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

    async def async_update_system_flags(self) -> None:
        """Update Wiser system flags from µGateway."""
        _LOGGER.debug("Attempting to update system flags from µGateway...")
        self._system_flags = await self._api.async_get_system_flags()

    async def async_update_system_health(self) -> None:
        """Update Wiser system health from µGateway."""
        _LOGGER.debug("Attempting to update system health from µGateway...")
        self._system_health = await self._api.async_get_system_health()

    async def async_update_gateway_info(self) -> None:
        """Update Wiser gateway info from µGateway."""
        _LOGGER.debug("Attempting to update µGateway info...")
        self._gateway_info = await self._api.async_get_info_debug()

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

    def _sync_unknown_type_issues(
        self,
        items: list,
        kind: str,
        extra_log_attrs: list[str] | None = None,
    ) -> None:
        """Create or delete HA issues for items with unknown types."""
        for item in items:
            issue_id = f"unknown_{kind}_type_{item.id}"
            if type(item) is Load:
                extra_str = ""
                if extra_log_attrs:
                    extra_str = (
                        " ("
                        + ", ".join(
                            f"{a}: '{getattr(item, a)}'" for a in extra_log_attrs
                        )
                        + ")"
                    )
                _LOGGER.warning(
                    "%s %s ('%s') has unknown type '%s'%s and will be ignored",
                    kind.capitalize(),
                    item.id,
                    item.name,
                    item.type,
                    extra_str,
                )
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=f"unknown_{kind}_type",
                    translation_placeholders={
                        "item_type": str(item.type),
                        "item_id": str(item.id),
                        "item_name": str(item.name or item.id),
                    },
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
