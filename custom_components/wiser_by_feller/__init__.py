"""The Wiser by Feller integration."""

from __future__ import annotations

import logging
from typing import Any, NoReturn

from aiowiserbyfeller import Auth, UnsuccessfulRequest, WiserByFellerAPI
from aiowiserbyfeller.enum import BlinkPattern
from aiowiserbyfeller.util import parse_wiser_device_ref_c
from homeassistant.components.light import ATTR_RGB_COLOR
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    CONF_IMPORTUSER,
    DOMAIN,
    IMPORT_USER_UNKNOWN,
    LED_OFF_COLOR,
    MANUFACTURER,
    MIN_FIRMWARE_BUTTON_LED_OVERRIDE,
    MIN_FIRMWARE_MANAGED_BUTTONS,
    MIN_FIRMWARE_STATUS_LIGHT_COLOR_OFF,
)
from .coordinator import WiserCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_STATUS_LIGHT = "status_light"
SERVICE_SET_BUTTON_LED_OVERRIDE = "set_button_led_override"
SERVICE_CLEAR_BUTTON_LED_OVERRIDE = "clear_button_led_override"
SERVICE_FIND_BUTTON = "find_button"
SERVICE_REGISTER_BUTTON = "register_button"
SERVICE_UNREGISTER_BUTTON = "unregister_button"
SERVICE_CREATE_SYSTEM_FLAG = "create_system_flag"
SERVICE_UPDATE_SYSTEM_FLAG = "update_system_flag"
SERVICE_DELETE_SYSTEM_FLAG = "delete_system_flag"
SERVICE_ASSIGN_SCENE_FLAG = "assign_scene_flag"
SERVICE_UNASSIGN_SCENE_FLAG = "unassign_scene_flag"

ATTR_BUTTON_ID = "button_id"
ATTR_LED_INDEX = "led_index"
ATTR_EFFECT = "effect"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DEVICE = "device"
ATTR_CHANNEL = "channel"
ATTR_REGISTER_UNMANAGED = "register_unmanaged"
ATTR_COLOR_OFF = "color_off"
ATTR_SYMBOL = "symbol"
ATTR_VALUE = "value"
ATTR_NAME = "name"
ATTR_SCENE_ENTITY_ID = "scene_entity_id"
ATTR_FLAG_ENTITY_ID = "flag_entity_id"

SYSTEM_FLAG_SYMBOL_REGEX = r"^[A-Za-z0-9_]+$"


def rgb_tuple_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def validate_rgb_color(value: Any) -> tuple[int, int, int]:
    """Validate RGB color."""
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise vol.Invalid("RGB color must be a list of three integers")

    rgb = tuple(int(color) for color in value)
    if any(color < 0 or color > 255 for color in rgb):
        raise vol.Invalid("RGB values must be between 0 and 255")

    return rgb[0], rgb[1], rgb[2]


SET_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default="0"): vol.In(["0", "1"]),
        vol.Required(ATTR_RGB_COLOR, default=(0, 255, 0)): validate_rgb_color,
        vol.Required(ATTR_EFFECT, default=BlinkPattern.PERMANENT.value): vol.In(
            [pattern.value for pattern in BlinkPattern]
        ),
    }
)

CLEAR_BUTTON_LED_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
        vol.Required(ATTR_LED_INDEX, default="0"): vol.In(["0", "1"]),
    }
)

FIND_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_REGISTER_UNMANAGED, default=False): cv.boolean,
    }
)

REGISTER_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_DEVICE): vol.All(cv.string, vol.Match(r"^[0-9a-fA-F]{1,8}$")),
        vol.Required(ATTR_CHANNEL): cv.positive_int,
    }
)

UNREGISTER_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_BUTTON_ID): cv.positive_int,
    }
)

CREATE_SYSTEM_FLAG_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SYMBOL): vol.All(
            cv.string, vol.Match(SYSTEM_FLAG_SYMBOL_REGEX)
        ),
        vol.Optional(ATTR_VALUE, default=False): cv.boolean,
        vol.Optional(ATTR_NAME): cv.string,
    }
)

UPDATE_SYSTEM_FLAG_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_ENTITY_ID): cv.entity_id,
            vol.Optional(ATTR_SYMBOL): vol.All(
                cv.string, vol.Match(SYSTEM_FLAG_SYMBOL_REGEX)
            ),
            vol.Optional(ATTR_NAME): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_SYMBOL, ATTR_NAME),
)

DELETE_SYSTEM_FLAG_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})

ASSIGN_SCENE_FLAG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SCENE_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_FLAG_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_VALUE, default=True): cv.boolean,
    }
)

UNASSIGN_SCENE_FLAG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SCENE_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_FLAG_ENTITY_ID): cv.entity_id,
    }
)


def _require_firmware(
    coordinator: WiserCoordinator,
    min_firmware: tuple[int, ...],
) -> None:
    """Raise ServiceValidationError if the gateway firmware is too old."""
    if not coordinator.supports_feature(min_firmware):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="firmware_too_old",
            translation_placeholders={
                "min_version": ".".join(str(x) for x in min_firmware),
                "current_version": (
                    coordinator.gateway_info["sw"]
                    if coordinator.gateway_info
                    else "unknown"
                ),
            },
        )


def _raise_button_led_error(err: UnsuccessfulRequest) -> None:
    """Translate a gateway error from a button LED request into a clear message."""
    if "fw-version too old" in str(err).lower():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_firmware_too_old",
        ) from err
    raise ServiceValidationError(str(err)) from err


def _resolve_coordinator(
    hass: HomeAssistant, entry_id: str | None = None
) -> WiserCoordinator:
    """Resolve the coordinator for a gateway-wide button service.

    Button ids are unique only per µGateway, so the caller selects the gateway
    via its config entry. When exactly one gateway is loaded the selection is
    optional and that gateway is used; with several loaded, one must be chosen.
    """
    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None
    ]

    if entry_id is not None:
        for entry in loaded:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )

    if not loaded:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )
    if len(loaded) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="specify_gateway",
        )
    return loaded[0].runtime_data


def _resolve_flag_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[WiserCoordinator, int]:
    """Resolve a system flag switch entity to its coordinator and flag id.

    The unique id of a flag switch is "<gateway>_flag_<id>", which also
    distinguishes flag switches from on/off load switches of this integration.
    """

    def _raise_not_a_flag() -> NoReturn:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_system_flag",
            translation_placeholders={"entity_id": entity_id},
        )

    entry = er.async_get(hass).async_get(entity_id)
    if (
        entry is None
        or entry.platform != DOMAIN
        or "_flag_" not in (entry.unique_id or "")
    ):
        _raise_not_a_flag()

    try:
        flag_id = int(entry.unique_id.rsplit("_flag_", 1)[1])
    except ValueError:
        _raise_not_a_flag()

    config_entry = (
        hass.config_entries.async_get_entry(entry.config_entry_id)
        if entry.config_entry_id is not None
        else None
    )
    if (
        config_entry is None
        or config_entry.state is not ConfigEntryState.LOADED
        or config_entry.runtime_data is None
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )
    return config_entry.runtime_data, flag_id


def _resolve_scene_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[WiserCoordinator, int]:
    """Resolve a Wiser scene entity to its coordinator and the scene's job id.

    The unique id of a scene entity is "<gateway>_scene_<id>".
    """

    def _raise_not_a_scene() -> NoReturn:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_wiser_scene",
            translation_placeholders={"entity_id": entity_id},
        )

    entry = er.async_get(hass).async_get(entity_id)
    if (
        entry is None
        or entry.platform != DOMAIN
        or "_scene_" not in (entry.unique_id or "")
    ):
        _raise_not_a_scene()

    try:
        scene_id = int(entry.unique_id.rsplit("_scene_", 1)[1])
    except ValueError:
        _raise_not_a_scene()

    config_entry = (
        hass.config_entries.async_get_entry(entry.config_entry_id)
        if entry.config_entry_id is not None
        else None
    )
    if (
        config_entry is None
        or config_entry.state is not ConfigEntryState.LOADED
        or config_entry.runtime_data is None
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_gateway_loaded",
        )

    coordinator: WiserCoordinator = config_entry.runtime_data
    scene = (coordinator.scenes or {}).get(scene_id)
    if scene is None:
        _raise_not_a_scene()
    return coordinator, scene.job


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Wiser by Feller integration.

    All service actions are registered here, once per integration load, so they
    exist even when no config entry is loaded and are never re-registered or
    removed per entry.
    """

    async def handle_status_light(call: ServiceCall) -> None:
        device_id = call.data["device"]
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if device is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == DOMAIN and entry.runtime_data is not None:
                coordinator: WiserCoordinator = entry.runtime_data
                if ATTR_COLOR_OFF in call.data:
                    _require_firmware(coordinator, MIN_FIRMWARE_STATUS_LIGHT_COLOR_OFF)
                await coordinator.async_set_status_light(call)
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )

    async def async_set_button_led_override(call: ServiceCall) -> None:
        """Set button LED override."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        try:
            await coordinator.api.async_set_button_led(
                button_id=call.data[ATTR_BUTTON_ID],
                led_index=int(call.data[ATTR_LED_INDEX]),
                on=True,
                pattern=BlinkPattern(call.data[ATTR_EFFECT]),
                color=rgb_tuple_to_hex(call.data[ATTR_RGB_COLOR]),
            )
        except UnsuccessfulRequest as err:
            _raise_button_led_error(err)

    async def async_clear_button_led_override(call: ServiceCall) -> None:
        """Clear button LED override."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        try:
            await coordinator.api.async_set_button_led(
                button_id=call.data[ATTR_BUTTON_ID],
                led_index=int(call.data[ATTR_LED_INDEX]),
                on=False,
                pattern=BlinkPattern.PERMANENT,
                color=LED_OFF_COLOR,
            )
        except UnsuccessfulRequest as err:
            _raise_button_led_error(err)

    async def async_find_button_service(call: ServiceCall) -> dict[str, Any]:
        """Find a physical button by activating find-me mode."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_BUTTON_LED_OVERRIDE)
        register_unmanaged = call.data[ATTR_REGISTER_UNMANAGED]
        if register_unmanaged:
            # Fail fast so the user doesn't sit through the two-minute find-me
            # flow only to hit the firmware error when registering.
            _require_firmware(coordinator, MIN_FIRMWARE_MANAGED_BUTTONS)

        result = await coordinator.async_find_button()

        button_id = result.get("button_id")
        device = result.get("device")
        channel = result.get("channel")

        fields: dict = {"room_name": None, "device_name": None, "scene_name": None}

        if (
            button_id is None
            and device is not None
            and channel is not None
            and register_unmanaged
        ):
            button = await coordinator.async_register_button(device, channel)
            button_id = button.id

        if button_id is not None:
            fields = coordinator.resolve_managed_button_fields(button_id)
        elif device is not None:
            # The button exists physically but isn't managed by the gateway, so
            # there is nothing to control. Surface this as a validation error
            # naming the device and channel needed to register it.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unmanaged_button",
                translation_placeholders={
                    "device": str(device),
                    "channel": str(channel),
                },
            )

        return {
            "button_id": button_id,
            "device": device,
            "channel": channel,
            "room_name": fields["room_name"],
            "device_name": fields["device_name"],
            "scene_name": fields["scene_name"],
        }

    async def async_register_button_service(call: ServiceCall) -> dict[str, Any]:
        """Register an available (sleeping) button on the µGateway."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_MANAGED_BUTTONS)
        button = await coordinator.async_register_button(
            call.data[ATTR_DEVICE], call.data[ATTR_CHANNEL]
        )
        fields = coordinator.resolve_managed_button_fields(button.id)
        return {
            "button_id": button.id,
            "device": button.device,
            "channel": button.channel,
            "room_name": fields["room_name"],
            "device_name": fields["device_name"],
            "scene_name": fields["scene_name"],
        }

    async def async_unregister_button_service(call: ServiceCall) -> dict[str, Any]:
        """Unregister (delete) a managed button from the µGateway."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _require_firmware(coordinator, MIN_FIRMWARE_MANAGED_BUTTONS)
        button = await coordinator.async_unregister_button(call.data[ATTR_BUTTON_ID])
        return {
            "button_id": call.data[ATTR_BUTTON_ID],
            "device": button.device,
            "channel": button.channel,
        }

    def _flag_response(flag: Any) -> dict[str, Any]:
        return {
            "id": flag.id,
            "symbol": flag.symbol,
            "value": flag.value,
            "name": flag.name,
        }

    async def async_create_system_flag_service(call: ServiceCall) -> dict[str, Any]:
        """Create a new system flag on the µGateway."""
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        flag = await coordinator.async_create_system_flag(
            call.data[ATTR_SYMBOL],
            value=call.data[ATTR_VALUE],
            name=call.data.get(ATTR_NAME),
        )
        return _flag_response(flag)

    async def async_update_system_flag_service(call: ServiceCall) -> dict[str, Any]:
        """Update the symbol and/or name of an existing system flag."""
        coordinator, flag_id = _resolve_flag_entity(hass, call.data[ATTR_ENTITY_ID])
        flag = await coordinator.async_update_system_flag(
            flag_id,
            symbol=call.data.get(ATTR_SYMBOL),
            name=call.data.get(ATTR_NAME),
        )
        return _flag_response(flag)

    async def async_delete_system_flag_service(call: ServiceCall) -> dict[str, Any]:
        """Delete an existing system flag from the µGateway."""
        coordinator, flag_id = _resolve_flag_entity(hass, call.data[ATTR_ENTITY_ID])
        flag = await coordinator.async_delete_system_flag(flag_id)
        return _flag_response(flag)

    def _resolve_scene_and_flag(call: ServiceCall) -> tuple[WiserCoordinator, int, int]:
        """Resolve scene and flag entities, ensuring they share one µGateway."""
        coordinator, job_id = _resolve_scene_entity(
            hass, call.data[ATTR_SCENE_ENTITY_ID]
        )
        flag_coordinator, flag_id = _resolve_flag_entity(
            hass, call.data[ATTR_FLAG_ENTITY_ID]
        )
        if flag_coordinator is not coordinator:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_same_gateway",
            )
        return coordinator, job_id, flag_id

    async def async_assign_scene_flag_service(call: ServiceCall) -> dict[str, Any]:
        """Assign a system flag value to a scene on the µGateway."""
        coordinator, job_id, flag_id = _resolve_scene_and_flag(call)
        flag_values = await coordinator.async_assign_scene_flag(
            job_id, flag_id, call.data[ATTR_VALUE]
        )
        return {"job_id": job_id, "flag_values": flag_values}

    async def async_unassign_scene_flag_service(call: ServiceCall) -> dict[str, Any]:
        """Remove a system flag assignment from a scene on the µGateway."""
        coordinator, job_id, flag_id = _resolve_scene_and_flag(call)
        flag_values = await coordinator.async_unassign_scene_flag(job_id, flag_id)
        return {"job_id": job_id, "flag_values": flag_values}

    hass.services.async_register(DOMAIN, SERVICE_STATUS_LIGHT, handle_status_light)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BUTTON_LED_OVERRIDE,
        async_set_button_led_override,
        schema=SET_BUTTON_LED_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_BUTTON_LED_OVERRIDE,
        async_clear_button_led_override,
        schema=CLEAR_BUTTON_LED_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_BUTTON,
        async_find_button_service,
        schema=FIND_BUTTON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_BUTTON,
        async_register_button_service,
        schema=REGISTER_BUTTON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNREGISTER_BUTTON,
        async_unregister_button_service,
        schema=UNREGISTER_BUTTON_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_SYSTEM_FLAG,
        async_create_system_flag_service,
        schema=CREATE_SYSTEM_FLAG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SYSTEM_FLAG,
        async_update_system_flag_service,
        schema=UPDATE_SYSTEM_FLAG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SYSTEM_FLAG,
        async_delete_system_flag_service,
        schema=DELETE_SYSTEM_FLAG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ASSIGN_SCENE_FLAG,
        async_assign_scene_flag_service,
        schema=ASSIGN_SCENE_FLAG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNASSIGN_SCENE_FLAG,
        async_unassign_scene_flag_service,
        schema=UNASSIGN_SCENE_FLAG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiser by Feller from a config entry."""
    # Entries created before the import user was persisted have no record of the
    # user the configuration was copied from. The original choice is not
    # recoverable, so mark it explicitly as unknown rather than guessing a value
    # that would imply false certainty in diagnostics.
    if CONF_IMPORTUSER not in entry.data:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_IMPORTUSER: IMPORT_USER_UNKNOWN},
        )

    session = async_get_clientsession(hass)
    auth = Auth(session, entry.data["host"], token=entry.data["token"])
    api = WiserByFellerAPI(auth)

    wiser_coordinator = WiserCoordinator(
        hass, api, entry.data["host"], entry.data["token"], entry.options
    )
    wiser_coordinator.ws_init()

    entry.runtime_data = wiser_coordinator

    await wiser_coordinator.async_config_entry_first_refresh()
    await async_setup_gateway(hass, entry, wiser_coordinator)
    await async_remove_stale_devices(hass, entry, wiser_coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WiserCoordinator = entry.runtime_data
    await coordinator.ws_close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_stale_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: WiserCoordinator,
) -> None:
    """Remove device registry entries no longer present in the Wiser gateway.

    Only runs when the coordinator holds a complete picture of the loads and
    devices. If the gateway returned partial data (e.g. a transient failure or
    the "Allow missing µGateway data" option), the expected set would be
    incomplete, and we could wrongly delete valid devices together with their
    entities, history and automations. In that case we skip cleanup entirely.
    """
    if coord.loads is None or coord.devices is None:
        _LOGGER.debug("Skipping stale device cleanup: coordinator data is incomplete.")
        return

    device_registry = dr.async_get(hass)

    expected: set[str] = set()

    if coord.gateway is not None:
        expected.add(coord.gateway.combined_serial_number)
    else:
        expected.add(entry.title)

    for load in coord.loads.values():
        expected.add(f"{load.device}_{load.channel}")

    for device in coord.devices.values():
        expected.add(device.id)

    for hvac_group in (coord.hvac_groups or {}).values():
        if hvac_group.thermostat_ref is not None:
            expected.add(f"{hvac_group.thermostat_ref.unprefixed_address}_hvac_group")

    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if any(
            domain == DOMAIN and identifier not in expected
            for domain, identifier in device_entry.identifiers
        ):
            _LOGGER.debug(
                "Detaching stale device %s from config entry", device_entry.name
            )
            # Detach this config entry rather than deleting outright: HA removes
            # the device only if no other config entry still references it.
            device_registry.async_update_device(
                device_entry.id, remove_config_entry_id=entry.entry_id
            )


async def async_setup_gateway(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coord: WiserCoordinator,
) -> None:
    """Set up the gateway device."""
    assert coord.config_entry is not None
    if coord.gateway is None:
        _LOGGER.warning(
            "The gateway device is not recognized in the coordinator, which can happen if option "
            '"Allow missing µGateway data" is enabled. This leads to non-unique scene identifiers! '
            "Please fix the root cause and disable the option."
        )

        gateway_identifier = coord.config_entry.title
        name = "Unknown µGateway"
        model = None
        sw_version = None
        hw_version = None
    else:
        assert coord.gateway_info is not None
        gateway_identifier = coord.gateway.combined_serial_number
        generation = parse_wiser_device_ref_c(coord.gateway.c["comm_ref"])["generation"]
        name = f"{coord.config_entry.title} µGateway"
        model = coord.gateway.c_name
        sw_version = coord.gateway_info["sw"]
        hw_version = f"{generation} ({coord.gateway.c['comm_ref']})"

    area = None
    for output in coord.gateway.outputs if coord.gateway is not None else []:
        if "load" not in output:
            continue

        if coord.loads is None or coord.rooms is None:
            continue

        load = coord.loads.get(output["load"])
        if load is None:
            continue  # coord.loads only contains loads not marked as unused.

        if load.room is not None and load.room in coord.rooms:
            area = coord.rooms[load.room].get("name")

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        configuration_url=f"http://{coord.api_host}",
        identifiers={(DOMAIN, gateway_identifier)},
        manufacturer=MANUFACTURER,
        model=model,
        name=name,
        sw_version=sw_version,
        hw_version=hw_version,
        suggested_area=area,
    )
