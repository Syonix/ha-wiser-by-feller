"""Tests for the Wiser by Feller repair flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller.errors import UnexpectedGatewayResponse
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wiser_by_feller.const import DOMAIN
from custom_components.wiser_by_feller.repairs import (
    MissingDeviceDataRepairFlow,
    async_create_fix_flow,
)

MOCK_HOST = "192.168.1.100"
MOCK_TOKEN = "61b096f3-9f20-46db-932c-c8bbf7f6011d"


def _make_flow(hass, entry_id="entry1", device_id="00254a0", can_auto_fix=True):
    """Create a repair flow wired up with hass, like the flow manager does."""
    flow = MissingDeviceDataRepairFlow(
        {
            "entry_id": entry_id,
            "device_id": device_id,
            "can_auto_fix": can_auto_fix,
        }
    )
    flow.hass = hass
    return flow


async def test_async_create_fix_flow_returns_flow(hass):
    """The entry point returns the repair flow handler."""
    flow = await async_create_fix_flow(hass, "missing_device_data_00254a0", {})
    assert isinstance(flow, MissingDeviceDataRepairFlow)


async def test_first_step_explains_problem(hass):
    """Opening the repair shows an explanation form — it must not run the fix.

    Regression guard: a form returned without a ``data_schema`` is auto-submitted
    by the HA frontend, which executes the fix the moment the issue is clicked.
    """
    flow = _make_flow(hass)

    result = await flow.async_step_init(None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    # Without a schema the frontend skips the dialog and submits immediately.
    assert result["data_schema"] is not None
    assert result["description_placeholders"] == {"device_id": "00254a0"}


async def test_explanation_advances_to_confirm_without_fixing(hass):
    """Acknowledging the explanation leads to the fix-confirmation step only.

    The fix must not run yet: no entry lookup, no API calls — just the second
    form where the user actually decides to apply the fix.
    """
    coordinator = MagicMock()
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id)

    result = await flow.async_step_init({})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["data_schema"] is not None
    coordinator.api.async_refresh_device_properties.assert_not_called()


async def test_submit_success_creates_entry(hass):
    """Submitting refreshes the device, waits for complete data, reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    device = MagicMock()
    device.validate_data.return_value = None  # data is complete

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=True)
    coordinator.api.async_get_device = AsyncMock(return_value=device)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    with (
        patch("custom_components.wiser_by_feller.repairs.asyncio.sleep", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    coordinator.api.async_refresh_device_properties.assert_awaited_once_with("d1")
    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_submit_waits_for_data_then_succeeds(hass):
    """The flow polls until the gateway repopulates the data before reloading."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    incomplete = MagicMock()
    incomplete.validate_data.side_effect = UnexpectedGatewayResponse("missing")
    complete = MagicMock()
    complete.validate_data.return_value = None

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=True)
    # First two polls still incomplete, third one validates.
    coordinator.api.async_get_device = AsyncMock(
        side_effect=[incomplete, incomplete, complete]
    )
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    with (
        patch("custom_components.wiser_by_feller.repairs.asyncio.sleep", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert coordinator.api.async_get_device.await_count == 3
    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_submit_data_never_completes_redisplays_form(hass):
    """If the data stays incomplete, the flow gives up without reloading."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)

    incomplete = MagicMock()
    incomplete.validate_data.side_effect = UnexpectedGatewayResponse("missing")

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=True)
    coordinator.api.async_get_device = AsyncMock(return_value=incomplete)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    with (
        patch("custom_components.wiser_by_feller.repairs.asyncio.sleep", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "reload_failed"}
    mock_reload.assert_not_called()


async def test_submit_refresh_failure_redisplays_form(hass):
    """A refused refresh re-shows the form with an error, keeping the schema."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=False)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "refresh_failed"}
    assert result["data_schema"] is not None


async def test_submit_missing_entry_aborts(hass):
    """The flow aborts cleanly when the referenced config entry is gone."""
    flow = _make_flow(hass, entry_id="does-not-exist")

    result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "entry_not_found"


async def test_submit_succeeds_when_another_device_keeps_entry_unloaded(hass):
    """Fixing this device succeeds even if another broken device blocks loading.

    Success is scoped to this device's repair issue, not the whole entry: the
    entry stays unloaded because a second device is still broken (its issue
    persists), but this device's issue is gone, so the repair completes.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_ERROR)  # other device unloaded it

    # A different device is still broken after the reload; ours is resolved.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "missing_device_data_other",
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="missing_device_data",
    )

    device = MagicMock()
    device.validate_data.return_value = None  # our device's data is complete

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=True)
    coordinator.api.async_get_device = AsyncMock(return_value=device)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    with (
        patch("custom_components.wiser_by_feller.repairs.asyncio.sleep", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_submit_fails_when_this_device_issue_persists(hass):
    """If this device's issue is still present after reload, the repair errors."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    # Our device's issue is re-filed on reload — it is still broken.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "missing_device_data_d1",
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="missing_device_data",
    )

    device = MagicMock()
    device.validate_data.return_value = None  # poll briefly saw complete data

    coordinator = MagicMock()
    coordinator.api.async_refresh_device_properties = AsyncMock(return_value=True)
    coordinator.api.async_get_device = AsyncMock(return_value=device)
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, device_id="d1")

    with (
        patch("custom_components.wiser_by_feller.repairs.asyncio.sleep", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock()),
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "reload_failed"}


# ── legacy firmware (no automatic refresh endpoint) ──────────────────────────


async def test_legacy_first_step_offers_reload_not_fix(hass):
    """On old firmware the first screen is the reload step, not the refresh fix."""
    flow = _make_flow(hass, can_auto_fix=False)

    result = await flow.async_step_init(None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reload"
    assert result["data_schema"] is not None


async def test_legacy_reload_success_creates_entry(hass):
    """Reloading reloads the entry; a loaded entry afterwards finishes the flow."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    flow = _make_flow(hass, entry_id=entry.entry_id, can_auto_fix=False)

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        result = await flow.async_step_reload({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_legacy_reload_still_failing_shows_alternatives(hass):
    """If this device's issue persists after reload, the legacy error is shown."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_ERROR)
    # The device is still broken: its repair issue is (re-)filed on reload.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "missing_device_data_00254a0",
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="missing_device_data",
    )

    flow = _make_flow(hass, entry_id=entry.entry_id, can_auto_fix=False)

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        result = await flow.async_step_reload({})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reload"
    assert result["errors"] == {"base": "reload_failed_legacy"}


async def test_legacy_never_calls_refresh_api(hass):
    """The legacy path must never hit the refresh endpoint (it does not exist)."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": MOCK_HOST, "token": MOCK_TOKEN}
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    coordinator = MagicMock()
    entry.runtime_data = coordinator

    flow = _make_flow(hass, entry_id=entry.entry_id, can_auto_fix=False)

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        await flow.async_step_reload({})

    coordinator.api.async_refresh_device_properties.assert_not_called()
