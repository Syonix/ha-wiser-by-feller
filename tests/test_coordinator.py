"""Tests for WiserCoordinator."""

import asyncio
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


def test_ws_update_data_noop_when_states_none(coordinator):
    """ws_update_data returns early when _states is not yet populated."""
    coordinator._states = None

    with patch.object(coordinator, "async_set_updated_data") as mock_update:
        coordinator.ws_update_data({"load": {"id": 1, "state": {}}})

    mock_update.assert_not_called()
    assert coordinator._states is None
