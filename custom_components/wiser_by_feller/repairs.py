"""Repairs for the Wiser by Feller integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiowiserbyfeller.errors import UnexpectedGatewayResponse
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import voluptuous as vol

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_REFRESH_POLL_ATTEMPTS = 10
_REFRESH_POLL_INTERVAL = 2.0


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str] | None,
) -> RepairsFlow:
    """Create a repair flow for a fixable issue."""
    return MissingDeviceDataRepairFlow(data or {})


class MissingDeviceDataRepairFlow(RepairsFlow):
    """Repair flow for a device with missing µGateway data."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the repair flow."""
        self._data = data
        self._placeholders: dict[str, str] = {"device_id": data.get("device_id") or ""}
        # Older firmware lacks the automatic refresh endpoint; fall back to a
        # reload-only flow. Default to the automatic fix for backwards
        # compatibility with issues filed before this flag existed.
        self._can_auto_fix: bool = bool(data.get("can_auto_fix", True))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Explain the problem, branching on whether an automatic fix exists."""
        if not self._can_auto_fix:
            return await self.async_step_reload(user_input)

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                description_placeholders=self._placeholders,
            )

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Let the user decide to run the automatic fix, then perform it."""
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders=self._placeholders,
            )

        device_id = self._data.get("device_id") or ""

        entry = self._get_entry()
        if not isinstance(entry, ConfigEntry):  # async_abort() FlowResult
            return entry

        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None:
            return self.async_abort(reason="no_coordinator")

        try:
            success = await coordinator.api.async_refresh_device_properties(device_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Failed to refresh device properties for %s: %s", device_id, err
            )
            return self._error_form("confirm", "refresh_failed")

        if not success:
            return self._error_form("confirm", "refresh_failed")

        # The gateway re-reads the device asynchronously; wait until the data is
        # actually complete before reloading, otherwise validation fails again.
        if not await self._wait_for_complete_data(coordinator, device_id):
            return self._error_form("confirm", "reload_failed")

        return await self._reload_and_finish("confirm", "reload_failed")

    async def async_step_reload(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Explain the legacy situation and offer to reload the integration.

        On firmware older than 6.0.40 there is no refresh endpoint, so the best
        the integration can do is reload and re-check after the user resolves the
        problem manually (firmware update, power-cycle, or bypass option).
        """
        if user_input is None:
            return self.async_show_form(
                step_id="reload",
                data_schema=vol.Schema({}),
                description_placeholders=self._placeholders,
            )

        return await self._reload_and_finish("reload", "reload_failed_legacy")

    async def _wait_for_complete_data(self, coordinator: Any, device_id: str) -> bool:
        """Poll the device until its identifying data validates, or time out."""
        for attempt in range(_REFRESH_POLL_ATTEMPTS):
            await asyncio.sleep(_REFRESH_POLL_INTERVAL)
            try:
                device = await coordinator.api.async_get_device(device_id)
                device.validate_data()
            except UnexpectedGatewayResponse:
                continue  # still incomplete, give the gateway more time
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "Polling device %s after refresh failed (attempt %s): %s",
                    device_id,
                    attempt + 1,
                    err,
                )
                continue
            return True
        return False

    def _get_entry(self) -> ConfigEntry | data_entry_flow.FlowResult:
        """Return the config entry, or an abort FlowResult if unavailable."""
        entry_id = self._data.get("entry_id")
        if not entry_id:
            return self.async_abort(reason="missing_data")

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")

        return entry

    async def _reload_and_finish(
        self, step_id: str, error: str
    ) -> data_entry_flow.FlowResult:
        """Reload the entry and finish if *this* device's data is now valid.

        Success is scoped to this device, not the whole entry: on reload the
        coordinator re-files ``missing_device_data_<id>`` for every device that
        still has incomplete data. The repair is therefore done once our
        device's issue is gone — even if other broken devices keep the entry
        from fully loading (each has its own repair).
        """
        entry = self._get_entry()
        if not isinstance(entry, ConfigEntry):  # async_abort() FlowResult
            return entry

        try:
            await self.hass.config_entries.async_reload(entry.entry_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to reload entry %s: %s", entry.entry_id, err)
            return self._error_form(step_id, error)

        if not self._device_issue_resolved():
            return self._error_form(step_id, error)

        return self.async_create_entry(data={})

    def _device_issue_resolved(self) -> bool:
        """Return True if this device no longer has a missing-data repair issue."""
        device_id = self._data.get("device_id") or "unknown"
        registry = ir.async_get(self.hass)
        return (
            registry.async_get_issue(DOMAIN, f"missing_device_data_{device_id}") is None
        )

    def _error_form(self, step_id: str, error: str) -> data_entry_flow.FlowResult:
        """Re-show the given step with an error message."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({}),
            errors={"base": error},
            description_placeholders=self._placeholders,
        )
