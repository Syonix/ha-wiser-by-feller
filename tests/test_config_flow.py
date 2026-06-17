"""Tests for the Wiser by Feller config flow."""

from unittest.mock import AsyncMock, patch

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ConnectionTimeoutError
from aiowiserbyfeller import UnsuccessfulRequest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wiser_by_feller.const import CONF_IMPORTUSER, DOMAIN
from custom_components.wiser_by_feller.exceptions import CannotConnect, InvalidAuth

MOCK_HOST = "192.168.1.100"
MOCK_SN = "ABC123DEF456"
MOCK_TOKEN = "test-token-12345"
MOCK_USERNAME = "homeassistant"
MOCK_IMPORT_USER = "admin"
MOCK_SITE_NAME = "My Home"
MOCK_INFO = {"sn": MOCK_SN, "hostname": "wiser-test"}
MOCK_SITE = {"name": MOCK_SITE_NAME}

USER_INPUT = {
    CONF_HOST: MOCK_HOST,
    CONF_USERNAME: MOCK_USERNAME,
    CONF_IMPORTUSER: MOCK_IMPORT_USER,
}


# ---------------------------------------------------------------------------
# User flow
# ---------------------------------------------------------------------------


async def test_form_shows_user_step(hass: HomeAssistant) -> None:
    """Initiating the flow shows the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_form_success(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """A valid submission creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_SITE_NAME
    assert result["data"] == {
        "host": MOCK_HOST,
        "token": MOCK_TOKEN,
        "sn": MOCK_SN,
        "username": MOCK_USERNAME,
        "title": MOCK_SITE_NAME,
    }
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_form_cannot_connect(hass: HomeAssistant, mock_setup_entry) -> None:
    """A connection failure shows the cannot_connect error."""
    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_unsuccessful_request(hass: HomeAssistant) -> None:
    """An UnsuccessfulRequest error shows the cannot_connect error."""
    mock_api = AsyncMock()
    mock_api.async_get_info.side_effect = UnsuccessfulRequest("error")

    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        return_value=mock_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_invalid_auth(hass: HomeAssistant) -> None:
    """An InvalidAuth exception shows the invalid_auth error."""
    mock_api = AsyncMock()
    mock_api.async_get_info.return_value = MOCK_INFO
    mock_api.async_get_site_info.return_value = MOCK_SITE
    mock_auth = AsyncMock()
    mock_auth.claim.side_effect = InvalidAuth

    with (
        patch(
            "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
            return_value=mock_api,
        ),
        patch(
            "custom_components.wiser_by_feller.config_flow.Auth",
            return_value=mock_auth,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_invalid_import_user(hass: HomeAssistant) -> None:
    """A 'not a directory' error shows the invalid_import_user error."""
    mock_api = AsyncMock()
    mock_api.async_get_info.return_value = MOCK_INFO
    mock_api.async_get_site_info.return_value = MOCK_SITE
    mock_auth = AsyncMock()
    mock_auth.claim.side_effect = CannotConnect("not a directory")

    with (
        patch(
            "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
            return_value=mock_api,
        ),
        patch(
            "custom_components.wiser_by_feller.config_flow.Auth",
            return_value=mock_auth,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_import_user"}


async def test_form_no_site_info(hass: HomeAssistant) -> None:
    """A 'no site info' error shows the no_site_info error."""
    mock_api = AsyncMock()
    mock_api.async_get_info.return_value = MOCK_INFO
    mock_api.async_get_site_info.side_effect = UnsuccessfulRequest("no site info")

    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        return_value=mock_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_site_info"}


async def test_form_connection_timeout(hass: HomeAssistant) -> None:
    """A connection timeout shows the connection_timeout error."""
    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=ConnectionTimeoutError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "connection_timeout"}


async def test_form_not_wiser_gateway(hass: HomeAssistant) -> None:
    """A 404 response aborts with not_wiser_gateway."""
    error = ClientResponseError(None, None, status=404)
    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=error,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_wiser_gateway"


async def test_form_already_configured(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """Submitting a duplicate host aborts the flow."""
    # First entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    # Second entry with same serial
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"], user_input=USER_INPUT
    )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# DHCP discovery
# ---------------------------------------------------------------------------


async def test_dhcp_discovery_shows_user_form(
    hass: HomeAssistant, mock_wiser_api
) -> None:
    """DHCP discovery pre-fills the host and shows the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip=MOCK_HOST,
            hostname="wiser-test",
            macaddress="aabbcc112233",
        ),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_dhcp_discovery_not_wiser_gateway(hass: HomeAssistant) -> None:
    """DHCP discovery aborts for non-Wiser devices."""
    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=Exception("not a wiser device"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip=MOCK_HOST,
                hostname="other-device",
                macaddress="aabbcc112233",
            ),
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_wiser_gateway"


async def test_dhcp_discovery_already_configured(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """DHCP discovery aborts if the device is already configured."""
    # Configure the entry first
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    # DHCP discovery for the same serial
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip=MOCK_HOST,
            hostname="wiser-test",
            macaddress="aabbcc112233",
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Zeroconf discovery
# ---------------------------------------------------------------------------


async def test_zeroconf_discovery_shows_user_form(
    hass: HomeAssistant, mock_wiser_api
) -> None:
    """Zeroconf discovery pre-fills the host and shows the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=MOCK_HOST,
            ip_addresses=[MOCK_HOST],
            hostname="wiser-test.local.",
            name="wiser-test._http._tcp.local.",
            port=80,
            properties={},
            type="_http._tcp.local.",
        ),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_zeroconf_discovery_not_wiser_gateway(hass: HomeAssistant) -> None:
    """Zeroconf discovery aborts for non-Wiser devices."""
    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=Exception("not a wiser device"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=ZeroconfServiceInfo(
                ip_address=MOCK_HOST,
                ip_addresses=[MOCK_HOST],
                hostname="other.local.",
                name="other._http._tcp.local.",
                port=80,
                properties={},
                type="_http._tcp.local.",
            ),
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_wiser_gateway"


async def test_zeroconf_discovery_already_configured(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """Zeroconf discovery aborts if the device is already configured."""
    # Configure the entry first
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    # Zeroconf discovery for the same serial
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=MOCK_HOST,
            ip_addresses=[MOCK_HOST],
            hostname="wiser-test.local.",
            name="wiser-test._http._tcp.local.",
            port=80,
            properties={},
            type="_http._tcp.local.",
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Reauth flow
# ---------------------------------------------------------------------------


async def test_reauth_success(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """A valid reauth submission updates the config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": MOCK_HOST,
            "token": "old-token",
            "sn": MOCK_SN,
            "username": MOCK_USERNAME,
            "title": MOCK_SITE_NAME,
        },
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == MOCK_TOKEN


async def test_reauth_cannot_connect(hass: HomeAssistant, mock_setup_entry) -> None:
    """A connection failure during reauth shows the cannot_connect error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": MOCK_HOST,
            "token": "old-token",
            "sn": MOCK_SN,
            "username": MOCK_USERNAME,
            "title": MOCK_SITE_NAME,
        },
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_invalid_auth(hass: HomeAssistant, mock_setup_entry) -> None:
    """An auth failure during reauth shows the invalid_auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": MOCK_HOST,
            "token": "old-token",
            "sn": MOCK_SN,
            "username": MOCK_USERNAME,
            "title": MOCK_SITE_NAME,
        },
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    mock_api = AsyncMock()
    mock_api.async_get_info.return_value = MOCK_INFO
    mock_api.async_get_site_info.return_value = MOCK_SITE
    mock_auth = AsyncMock()
    mock_auth.claim.side_effect = InvalidAuth

    with (
        patch(
            "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
            return_value=mock_api,
        ),
        patch(
            "custom_components.wiser_by_feller.config_flow.Auth",
            return_value=mock_auth,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


async def test_reconfigure_success(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """A valid reconfigure submission updates the host and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": MOCK_HOST,
            "token": "old-token",
            "sn": MOCK_SN,
            "username": MOCK_USERNAME,
            "title": MOCK_SITE_NAME,
        },
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    new_host = "192.168.1.200"
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: new_host,
            CONF_USERNAME: MOCK_USERNAME,
            CONF_IMPORTUSER: MOCK_IMPORT_USER,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == new_host
    assert entry.data["token"] == MOCK_TOKEN


async def test_reconfigure_wrong_device(hass: HomeAssistant, mock_setup_entry) -> None:
    """Reconfigure aborts when the new address points to a different gateway."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": MOCK_HOST, "token": "old-token", "sn": MOCK_SN},
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    different_sn = "DIFFERENT000"
    mock_api = AsyncMock()
    mock_api.async_get_info.return_value = {
        "sn": different_sn,
        "hostname": "other-wiser",
    }
    mock_api.async_get_site_info.return_value = MOCK_SITE
    mock_auth = AsyncMock()
    mock_auth.claim.return_value = MOCK_TOKEN

    with (
        patch(
            "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
            return_value=mock_api,
        ),
        patch(
            "custom_components.wiser_by_feller.config_flow.Auth",
            return_value=mock_auth,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """A connection failure during reconfigure shows the cannot_connect error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": MOCK_HOST, "token": "old-token", "sn": MOCK_SN},
        unique_id=MOCK_SN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    with patch(
        "custom_components.wiser_by_feller.config_flow.WiserByFellerAPI",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


async def test_options_flow_shows_form(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """The options flow shows the options form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_save(
    hass: HomeAssistant, mock_wiser_api, mock_setup_entry
) -> None:
    """Submitting the options form saves the options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"allow_missing_gateway_data": True},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"allow_missing_gateway_data": True}
