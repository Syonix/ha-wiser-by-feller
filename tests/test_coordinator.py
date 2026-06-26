"""Tests for WiserCoordinator."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import (
    AuthorizationFailed,
    Load,
    Sensor,
    UnauthorizedUser,
    UnsuccessfulRequest,
)
from aiowiserbyfeller.const import LOAD_SUBTYPE_ONOFF_DTO, LOAD_TYPE_ONOFF
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.wiser_by_feller.const import DOMAIN
from custom_components.wiser_by_feller.coordinator import WiserCoordinator

MOCK_HOST = "192.168.1.100"
MOCK_TOKEN = "61b096f3-9f20-46db-932c-c8bbf7f6011d"
# /api/info/debug response shapes — hw is a hardware version number, not a label
MOCK_GATEWAY_INFO = {
    "product": "9020.001.002",
    "instance_id": 1800,
    "sn": "20012161",
    "api": "6.0",
    "sw": "2.1.3",
    "boot": "1.3.0",
    "hw": "3",
}
MOCK_GATEWAY_INFO_GEN_A = {
    "product": "9020.001.001",
    "instance_id": 1200,
    "sn": "17210151",
    "api": "5.0",
    "sw": "1.8.2",
    "boot": "1.2.0",
    "hw": "2",
}

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_bare_load(
    load_id=99, name="Mystery Load", load_type="unknown_xyz", sub_type=None
):
    """Create a genuine Load instance for _sync_unknown_type_issues tests.

    The coordinator checks `type(item) is Load` to detect base-class (unknown-type) loads.
    Load.id is a read-only property backed by raw_data, so we must use the real constructor.
    """
    return Load(
        {"id": load_id, "name": name, "type": load_type, "sub_type": sub_type},
        MagicMock(),
    )


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_api():
    """Return a fully mocked WiserByFellerAPI."""
    api = AsyncMock()
    api.auth = MagicMock()
    api.auth.host = MOCK_HOST

    api.async_get_info_debug = AsyncMock(return_value=MOCK_GATEWAY_INFO)
    api.async_get_used_loads = AsyncMock(return_value=[])
    api.async_get_rooms = AsyncMock(return_value=[])
    api.async_get_devices_detail = AsyncMock(return_value=[])
    api.async_get_jobs = AsyncMock(return_value=[])
    api.async_get_scenes = AsyncMock(return_value=[])
    api.async_get_system_flags = AsyncMock(return_value=[])
    api.async_get_sensors = AsyncMock(return_value=[])
    api.async_get_hvac_groups = AsyncMock(return_value=[])
    api.async_get_hvac_group_states = AsyncMock(return_value=[])
    api.async_get_loads_state = AsyncMock(return_value=[])
    api.async_get_system_health = AsyncMock(return_value=MOCK_GATEWAY_INFO)
    api.async_ping_device = AsyncMock(return_value=True)
    return api


@pytest.fixture
def coordinator(hass, mock_api):
    """Return a WiserCoordinator with a mocked websocket (is_idle=False)."""
    mock_ws = MagicMock()
    mock_ws.is_idle.return_value = False
    mock_ws.async_close = AsyncMock()

    with patch(
        "custom_components.wiser_by_feller.coordinator.Websocket",
        return_value=mock_ws,
    ):
        return WiserCoordinator(hass, mock_api, MOCK_HOST, MOCK_TOKEN, {})


# ── gateway version ──────────────────────────────────────────────────────────


def test_is_gen_b_true(coordinator):
    """Gateway api '6.0' → is_gen_b is True."""
    coordinator._gateway_info = MOCK_GATEWAY_INFO  # api: "6.0"
    assert coordinator.is_gen_b is True


def test_is_gen_b_false(coordinator):
    """Gateway api '5.0' → is_gen_b is False."""
    coordinator._gateway_info = MOCK_GATEWAY_INFO_GEN_A  # api: "5.0"
    assert coordinator.is_gen_b is False


def test_is_gen_b_false_when_no_gateway_info(coordinator):
    """gateway_info=None → is_gen_b is False."""
    coordinator._gateway_info = None
    assert coordinator.is_gen_b is False


def test_gateway_api_major_version_parsed(coordinator):
    """gateway_api_major_version parses the major integer from api '6.0'."""
    coordinator._gateway_info = MOCK_GATEWAY_INFO
    assert coordinator.gateway_api_major_version == 6


def test_gateway_supports_sensors_gen_b(coordinator):
    """Gen B gateway (api >= 6) → gateway_supports_sensors is True."""
    coordinator._gateway_info = MOCK_GATEWAY_INFO
    assert coordinator.gateway_supports_sensors is True


def test_gateway_supports_sensors_gen_a(coordinator):
    """Gen A gateway (api < 6) → gateway_supports_sensors is False."""
    coordinator._gateway_info = MOCK_GATEWAY_INFO_GEN_A
    assert coordinator.gateway_supports_sensors is False


# ── _async_update_data error handling ────────────────────────────────────────


async def test_timeout_raises_update_failed(coordinator, mock_api):
    """asyncio.TimeoutError from the API is converted to UpdateFailed."""
    mock_api.async_get_info_debug.side_effect = asyncio.TimeoutError
    with pytest.raises(UpdateFailed, match="Timeout"):
        await coordinator._async_update_data()


async def test_authorization_failed_raises_config_entry_auth_failed(
    coordinator, mock_api
):
    """AuthorizationFailed from the API is converted to ConfigEntryAuthFailed."""
    mock_api.async_get_info_debug.side_effect = AuthorizationFailed
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_unauthorized_user_raises_config_entry_auth_failed(coordinator, mock_api):
    """UnauthorizedUser from the API is converted to ConfigEntryAuthFailed."""
    mock_api.async_get_info_debug.side_effect = UnauthorizedUser
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_unsuccessful_request_raises_update_failed(coordinator, mock_api):
    """UnsuccessfulRequest from the API is converted to UpdateFailed."""
    mock_api.async_get_info_debug.side_effect = UnsuccessfulRequest("boom")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# ── lazy loading ──────────────────────────────────────────────────────────────


async def test_loads_fetched_only_once(coordinator, mock_api):
    """`_loads` is None on first call → fetched. Non-None on second call → skipped."""
    await coordinator._async_update_data()
    assert mock_api.async_get_used_loads.call_count == 1

    await coordinator._async_update_data()
    assert mock_api.async_get_used_loads.call_count == 1


async def test_devices_fetched_only_once(coordinator, mock_api):
    """Devices are fetched on the first update and skipped on subsequent updates."""
    await coordinator._async_update_data()
    assert mock_api.async_get_devices_detail.call_count == 1

    await coordinator._async_update_data()
    assert mock_api.async_get_devices_detail.call_count == 1


# ── unknown type issues ───────────────────────────────────────────────────────


def test_sync_unknown_type_issues_creates_issue_for_base_load(coordinator, hass):
    """Items of exact type Load (not a subclass) → ir.async_create_issue called."""
    unknown_load = _make_bare_load()
    assert type(unknown_load) is Load  # guard: ensure the helper worked

    with (
        patch(
            "custom_components.wiser_by_feller.coordinator.ir.async_create_issue"
        ) as mock_create,
        patch("custom_components.wiser_by_feller.coordinator.ir.async_delete_issue"),
    ):
        coordinator._sync_unknown_type_issues([unknown_load], "load")
        mock_create.assert_called_once()
        # issue_id is the 3rd positional argument to ir.async_create_issue
        assert mock_create.call_args.args[2] == "unknown_load_type_99"


def test_sync_unknown_type_issues_deletes_issue_for_known_type(coordinator):
    """Items that are NOT base Load (subclass or other type) → ir.async_delete_issue called."""
    # MagicMock(spec=Sensor): type(item) is not Load → goes to else branch
    known_sensor = MagicMock(spec=Sensor)
    known_sensor.id = 10

    with patch(
        "custom_components.wiser_by_feller.coordinator.ir.async_delete_issue"
    ) as mock_delete:
        coordinator._sync_unknown_type_issues([known_sensor], "sensor")
        mock_delete.assert_called_once()
        # issue_id passed as third positional argument
        assert mock_delete.call_args.args[2] == "unknown_sensor_type_10"


def test_sync_unknown_type_issues_passes_domain(coordinator):
    """Issue is registered under the WISER domain."""
    unknown_load = _make_bare_load(load_id=5)
    assert type(unknown_load) is Load

    with patch(
        "custom_components.wiser_by_feller.coordinator.ir.async_create_issue"
    ) as mock_create:
        coordinator._sync_unknown_type_issues([unknown_load], "load")
        call_args = mock_create.call_args
        assert call_args.args[1] == DOMAIN  # second positional arg is domain


# ── async_is_onoff_impulse_load ───────────────────────────────────────────────


async def test_async_is_onoff_impulse_load_true(coordinator, mock_api):
    """OnOff DTO load with delay_ms < 10000 is identified as an impulse load."""
    load = MagicMock()
    load.type = LOAD_TYPE_ONOFF
    load.sub_type = LOAD_SUBTYPE_ONOFF_DTO
    load.device = "DEV001"
    load.channel = 0

    mock_api.async_get_device_config.return_value = {"outputs": [{"delay_ms": 500}]}

    result = await coordinator.async_is_onoff_impulse_load(load)
    assert result is True


async def test_async_is_onoff_impulse_load_false_long_delay(coordinator, mock_api):
    """OnOff DTO load with delay_ms >= 10000 is a Minuterie, not an impulse load."""
    load = MagicMock()
    load.type = LOAD_TYPE_ONOFF
    load.sub_type = LOAD_SUBTYPE_ONOFF_DTO
    load.device = "DEV001"
    load.channel = 0

    # delay >= 10000 ms → Minuterie, not impulse
    mock_api.async_get_device_config.return_value = {"outputs": [{"delay_ms": 30000}]}

    result = await coordinator.async_is_onoff_impulse_load(load)
    assert result is False


async def test_async_is_onoff_impulse_load_false_wrong_type(coordinator):
    """Non-OnOff load type is never an impulse load."""
    load = MagicMock()
    load.type = "dim"
    load.sub_type = None

    result = await coordinator.async_is_onoff_impulse_load(load)
    assert result is False


# ── ws_update_data ────────────────────────────────────────────────────────────


def test_ws_update_data_load_updates_states(coordinator):
    """WebSocket 'load' event updates coordinator._states for that load ID."""
    coordinator._states = {1: {"bri": 0}}
    new_state = {"bri": 10000}

    with patch.object(coordinator, "async_set_updated_data"):
        coordinator.ws_update_data({"load": {"id": 1, "state": new_state}})

    assert coordinator._states[1] == new_state


def test_ws_update_data_sensor_updates_states(coordinator):
    """WebSocket 'sensor' event updates coordinator._states for that sensor ID."""
    coordinator._states = {5: {}}
    sensor_data = {"id": 5, "temperature": 21.5}

    with patch.object(coordinator, "async_set_updated_data"):
        coordinator.ws_update_data({"sensor": sensor_data})

    assert coordinator._states[5] == sensor_data


def test_ws_update_data_hvacgroup_updates_states(coordinator):
    """WebSocket 'hvacgroup' event updates coordinator._states for that group ID."""
    coordinator._states = {10: {}}
    hvac_state = {"mode": "heat", "temp": 22.0}

    with patch.object(coordinator, "async_set_updated_data"):
        coordinator.ws_update_data({"hvacgroup": {"id": 10, "state": hvac_state}})

    assert coordinator._states[10] == hvac_state


def test_ws_update_data_button_fires_bus_event(coordinator):
    """WebSocket 'button' event is fired on the bus and does not touch state."""
    coordinator._states = {}
    coordinator.config_entry = MagicMock(entry_id="abc123")
    coordinator.hass = MagicMock()

    with patch.object(coordinator, "async_set_updated_data") as mock_update:
        coordinator.ws_update_data(
            {"button": {"id": 53, "cmd": {"event": "press", "type": "down"}}}
        )

    mock_update.assert_not_called()  # button events don't refresh entity state
    coordinator.hass.bus.async_fire.assert_called_once_with(
        "wiser_by_feller_button_event",
        {
            "config_entry_id": "abc123",
            "button_id": 53,
            "event": "press",
            "type": "down",
        },
    )


def test_ws_update_data_noop_when_states_none(coordinator):
    """ws_update_data returns early when _states is not yet populated."""
    coordinator._states = None

    with patch.object(coordinator, "async_set_updated_data") as mock_update:
        coordinator.ws_update_data({"load": {"id": 1, "state": {}}})

    mock_update.assert_not_called()
    assert coordinator._states is None


# ── resolve_managed_button_fields ─────────────────────────────────────────────


def _make_button(button_id=1, device_id="00019edc", channel=0, job_id=None):
    button = MagicMock()
    button.id = button_id
    button.device = device_id
    button.channel = channel
    raw = {"id": button_id, "device": device_id, "channel": channel}
    if job_id is not None:
        raw["job"] = job_id
    button.raw_data = raw
    return button


def _make_device_for_coord(
    comm_name_c="Dimmer Plus", comm_name_a="Dimmer", outputs=None
):
    device = MagicMock()
    device.c = {"comm_name": comm_name_c, "comm_ref": "ABC", "fw_version": "1.0"}
    device.a = {"comm_name": comm_name_a, "comm_ref": "ABC", "fw_version": "1.0"}
    device.outputs = outputs or []
    return device


def _make_scene_for_coord(scene_id=1, name="Movie Night", job_id=100):
    scene = MagicMock()
    scene.id = scene_id
    scene.name = name
    scene.job = job_id
    return scene


def test_resolve_button_fields_empty_when_managed_buttons_none(coordinator):
    """Returns all-None when managed_buttons has not been loaded yet."""
    coordinator._managed_buttons = None
    coordinator._devices = {}
    assert coordinator.resolve_managed_button_fields(1) == {
        "room_name": None,
        "device_name": None,
        "scene_name": None,
    }


def test_resolve_button_fields_empty_when_devices_none(coordinator):
    """Returns all-None when the device list has not been loaded yet."""
    coordinator._managed_buttons = {1: _make_button(button_id=1)}
    coordinator._devices = None
    assert coordinator.resolve_managed_button_fields(1) == {
        "room_name": None,
        "device_name": None,
        "scene_name": None,
    }


def test_resolve_button_fields_empty_when_button_not_found(coordinator):
    """Returns all-None when the button ID is not in managed_buttons."""
    coordinator._managed_buttons = {}
    coordinator._devices = {}
    assert coordinator.resolve_managed_button_fields(99) == {
        "room_name": None,
        "device_name": None,
        "scene_name": None,
    }


def test_resolve_button_fields_empty_when_device_not_found(coordinator):
    """Returns all-None when the button's device ID is not in the devices dict."""
    coordinator._managed_buttons = {1: _make_button(button_id=1, device_id="missing")}
    coordinator._devices = {}
    assert coordinator.resolve_managed_button_fields(1) == {
        "room_name": None,
        "device_name": None,
        "scene_name": None,
    }


def test_resolve_button_fields_returns_device_name_without_room(coordinator):
    """Returns device_name and None room when the device has no linked load or room."""
    coordinator._managed_buttons = {1: _make_button(button_id=1, device_id="dev1")}
    coordinator._devices = {"dev1": _make_device_for_coord()}
    coordinator._loads = {}
    coordinator._rooms = {}
    coordinator._scenes = {}
    result = coordinator.resolve_managed_button_fields(1)
    assert result["device_name"] is not None
    assert result["room_name"] is None
    assert result["scene_name"] is None


def test_resolve_button_fields_returns_room_from_load(coordinator):
    """Returns room name resolved via the device output → load → room chain."""
    load = MagicMock()
    load.room = 42
    device = _make_device_for_coord(outputs=[{"load": 7}])
    coordinator._managed_buttons = {1: _make_button(button_id=1, device_id="dev1")}
    coordinator._devices = {"dev1": device}
    coordinator._loads = {7: load}
    coordinator._rooms = {42: {"name": "Living Room"}}
    coordinator._scenes = {}
    result = coordinator.resolve_managed_button_fields(1)
    assert result["room_name"] == "Living Room"


def test_resolve_button_fields_returns_scene_from_matching_job(coordinator):
    """Returns scene name when the button's job ID matches a scene's job ID."""
    coordinator._managed_buttons = {
        1: _make_button(button_id=1, device_id="dev1", job_id=100)
    }
    coordinator._devices = {"dev1": _make_device_for_coord()}
    coordinator._loads = {}
    coordinator._rooms = {}
    coordinator._scenes = {1: _make_scene_for_coord(job_id=100, name="Movie Night")}
    result = coordinator.resolve_managed_button_fields(1)
    assert result["scene_name"] == "Movie Night"


def test_resolve_button_fields_scene_none_when_no_matching_job(coordinator):
    """Returns scene=None when no scene has a job that matches the button's job."""
    coordinator._managed_buttons = {
        1: _make_button(button_id=1, device_id="dev1", job_id=999)
    }
    coordinator._devices = {"dev1": _make_device_for_coord()}
    coordinator._loads = {}
    coordinator._rooms = {}
    coordinator._scenes = {1: _make_scene_for_coord(job_id=100)}
    assert coordinator.resolve_managed_button_fields(1)["scene_name"] is None


def test_resolve_button_fields_scene_none_when_button_has_no_job(coordinator):
    """Returns scene=None when the button has no job in its raw_data."""
    coordinator._managed_buttons = {1: _make_button(button_id=1, device_id="dev1")}
    coordinator._devices = {"dev1": _make_device_for_coord()}
    coordinator._loads = {}
    coordinator._rooms = {}
    coordinator._scenes = {1: _make_scene_for_coord(job_id=100)}
    assert coordinator.resolve_managed_button_fields(1)["scene_name"] is None


async def test_ws_idle_logs_warning_once(coordinator, mock_api, caplog):
    """WebSocket idle triggers a warning only on the first detection, not every poll."""
    coordinator._ws.is_idle.return_value = True

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    warnings = [r for r in caplog.records if "idle" in r.message.lower()]
    assert len(warnings) == 1
    assert coordinator._ws_was_idle is True


async def test_ws_idle_recovery_logs_info(coordinator, mock_api, caplog):
    """After being idle, a successful reconnect logs an info recovery message."""
    coordinator._ws_was_idle = True
    coordinator._ws.is_idle.return_value = False

    with caplog.at_level(logging.INFO):
        await coordinator._async_update_data()

    assert coordinator._ws_was_idle is False
    assert any("re-established" in r.message.lower() for r in caplog.records)


# ── status light ──────────────────────────────────────────────────────────────


def _status_light_call(**overrides):
    """Build a ServiceCall-like stub for async_set_status_light."""
    data = {
        "device": "000004d7",
        "channel": "0",
        "color": [26, 188, 242],
        "brightness_on": 100,
    }
    data.update(overrides)
    call = MagicMock()
    call.data = data
    return call


def _prepare_status_light(coordinator, mock_api):
    """Wire up the device lookups async_set_status_light needs."""
    device = MagicMock()
    device.serial_number = "20012161"
    coordinator._device_ids_by_serial = {"20012161": "wiser-device-1"}
    coordinator._devices = {"wiser-device-1": MagicMock(inputs=[0, 1, 2, 3])}
    mock_api.async_get_device_config = AsyncMock(return_value={"id": "config-7"})
    mock_api.async_set_device_input_config = AsyncMock()
    mock_api.async_apply_device_config = AsyncMock()
    return device


async def test_set_status_light_without_color_off_omits_color_keys(
    coordinator, mock_api
):
    """Without color_off, only `color` is sent (no foreground/background color)."""
    device = _prepare_status_light(coordinator, mock_api)

    with patch("custom_components.wiser_by_feller.coordinator.dr.async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = device
        await coordinator.async_set_status_light(_status_light_call())

    _, _, data = mock_api.async_set_device_input_config.call_args.args
    assert data["color"] == "#1abcf2"
    assert "foreground_color" not in data
    assert "background_color" not in data


async def test_set_status_light_with_color_off_sets_color_keys(coordinator, mock_api):
    """With color_off, foreground/background colors are sent and `color` stays foreground."""
    device = _prepare_status_light(coordinator, mock_api)

    with patch("custom_components.wiser_by_feller.coordinator.dr.async_get") as mock_dr:
        mock_dr.return_value.async_get.return_value = device
        await coordinator.async_set_status_light(
            _status_light_call(color_off=[0, 0, 0])
        )

    _, _, data = mock_api.async_set_device_input_config.call_args.args
    assert data["color"] == "#1abcf2"
    assert data["foreground_color"] == "#1abcf2"
    assert data["background_color"] == "#000000"
