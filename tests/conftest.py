"""Shared fixtures for Wiser by Feller integration tests."""

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


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
