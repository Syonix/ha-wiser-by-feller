"""Base entity class for Wiser by Feller integration."""

from __future__ import annotations

from aiowiserbyfeller import Device, Load
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .const import MANUFACTURER
from .coordinator import WiserCoordinator, get_unique_id
from .util import resolve_device_name


class WiserEntity(CoordinatorEntity):
    """Wiser by Feller base entity."""

    def __init__(
        self,
        coordinator: WiserCoordinator,
        load: Load | None,
        device: Device | None,
        room: dict | None,
    ) -> None:
        """Set up base entity."""
        super().__init__(coordinator)  # TODO: Is this required?

        if device is not None:
            # Support entities without Wiser device for HVAC groups.
            self.coordinator_context = (
                device.id if load is None else load.id
            )  # TODO: Suboptimal

            self._attr_raw_unique_id = get_unique_id(device, load)
            self._attr_unique_id = self._attr_raw_unique_id
            self._device_name = resolve_device_name(device, room, load)

        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_name = None
        self._device = device
        self._load = load
        self._room = room

    @property
    def raw_unique_id(self) -> str:
        """Raw unique ID based on device id and channel number (if applicable).

        This is required to identify the logical device in Home Assistant,
        as entities like the "identify" button, which do not have an own identifier,
        append their own suffix to the unique identifier for uniqueness. This would
        cause the same logical device to appear as two separate devices in HA.
        """
        return self._attr_raw_unique_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""

        if self._device is None:
            return None

        model_id = (
            f"{self._device.c['comm_ref']} + {self._device.a['comm_ref']}"
            if self._device.c["comm_ref"] != self._device.a["comm_ref"]
            else self._device.a["comm_ref"]
        )
        model = (
            self._device.a_name
            if self._device.c_name in self._device.a_name
            else f"{self._device.c_name} + {self._device.a_name}"
        )
        firmware = (
            f"{self._device.c['fw_version']} (Controls) / {self._device.a['fw_version']} (Actuator)"
            if self._device.c["fw_version"] != self._device.a["fw_version"]
            else self._device.a["fw_version"]
        )
        area = None if self._room is None else self._room["name"]
        via = (
            (DOMAIN, self.coordinator.gateway.combined_serial_number)
            if self.coordinator.gateway is not None
            else None
        )

        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    self.raw_unique_id,
                ),  # Either "<device-id> or <device-id>_<load-channel>"
            },
            name=resolve_device_name(self._device, self._room, self._load),
            manufacturer=MANUFACTURER,
            model=model,
            model_id=model_id,
            sw_version=firmware,
            serial_number=self._device.combined_serial_number,
            suggested_area=area,
            via_device=via,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated entity data from the coordinator."""
        self._load.raw_state = self.coordinator.states[self._load.id]
        self.async_write_ha_state()
