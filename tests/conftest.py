"""Shared fixtures for Wiser by Feller integration tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wiser_by_feller.const import DOMAIN
from custom_components.wiser_by_feller.coordinator import WiserCoordinator

pytest_plugins = "pytest_homeassistant_custom_component"

MOCK_HOST = "192.168.1.100"
MOCK_SN = "20012161"
MOCK_TOKEN = "61b096f3-9f20-46db-932c-c8bbf7f6011d"
# /api/info/debug response — hardware version "3" is the Gen B number; no uptime here
MOCK_GATEWAY_INFO = {
    "product": "9020.001.002",
    "instance_id": 1800,
    "sn": MOCK_SN,
    "api": "6.0",
    "sw": "2.1.3",
    "boot": "1.3.0",
    "hw": "3",
}
# /api/system/health response
MOCK_SYSTEM_HEALTH = {
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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom integrations discoverable in all tests."""
    return


@pytest.fixture
def mock_setup_entry():
    """Prevent the integration from actually being set up."""
    with patch(
        "custom_components.wiser_by_feller.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_wiser_api():
    """Patch Auth and WiserByFellerAPI to return predictable test data."""
    mock_api_instance = AsyncMock()
    mock_api_instance.async_get_info.return_value = {
        "sn": "ABC123DEF456",
        "hostname": "wiser-test",
    }
    mock_api_instance.async_get_site_info.return_value = {"name": "My Home"}

    mock_auth_instance = AsyncMock()
    mock_auth_instance.claim.return_value = "test-token-12345"

    with (
        patch(
            "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
            return_value=mock_api_instance,
        ),
        patch(
            "custom_components.wiser_by_feller.config_flow.Auth",
            return_value=mock_auth_instance,
        ),
    ):
        yield mock_api_instance, mock_auth_instance


@pytest.fixture
def mock_config_entry():
    """Return a MockConfigEntry for the wiser_by_feller domain."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Wiser",
        data={"host": MOCK_HOST, "token": MOCK_TOKEN},
        options={},
        unique_id=MOCK_SN,
    )


@pytest.fixture
def mock_gateway():
    """Return a mock gateway Device."""
    gw = MagicMock()
    gw.combined_serial_number = MOCK_SN
    gw.id = "0000072d"
    gw.c = {
        "comm_ref": "9020.001.002",
        "comm_name": "µGateway 4-fach",
        "fw_version": "0x00620a28",
    }
    gw.a = {
        "comm_ref": "9020.001.002",
        "comm_name": "µGateway 4-fach",
        "fw_version": "0x00620a28",
    }
    gw.c_name = "µGateway 4-fach"
    gw.a_name = "µGateway 4-fach"
    gw.outputs = []
    return gw


@pytest.fixture
def mock_coordinator(mock_config_entry, mock_gateway):
    """Return a MagicMock WiserCoordinator with sensible defaults."""
    coord = MagicMock(spec=WiserCoordinator)

    # DataUpdateCoordinator instance attributes not captured by spec
    coord.last_update_success = True

    # Async methods
    coord.async_config_entry_first_refresh = AsyncMock()
    coord.ws_close = AsyncMock()
    coord.async_set_status_light = AsyncMock()
    coord.async_ping_device = AsyncMock()
    coord.async_is_onoff_impulse_load = AsyncMock(return_value=False)

    # Sync methods
    coord.ws_init = MagicMock()

    # Data stores — start empty; tests populate as needed
    coord.loads = {}
    coord.states = {}
    coord.devices = {}
    coord.rooms = {}
    coord.scenes = {}
    coord.jobs = {}
    coord.sensors = {}
    coord.hvac_groups = {}
    coord.system_flags = []
    coord.system_health = MOCK_SYSTEM_HEALTH

    # Gateway
    coord.gateway = mock_gateway
    coord.gateway_info = MOCK_GATEWAY_INFO
    coord.gateway_api_major_version = 6
    coord.is_gen_b = True
    coord.gateway_supports_sensors = True
    coord.gateway_supports_hvac_groups = True
    coord.assigned_thermostats = {}

    # Config entry reference (used in switch.py / scene.py when gateway is None)
    coord.config_entry = mock_config_entry
    coord.api_host = MOCK_HOST

    return coord


@pytest.fixture
async def setup_integration(hass, mock_config_entry, mock_coordinator):
    """Set up the integration with a fully mocked coordinator."""
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
    return mock_config_entry
