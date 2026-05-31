"""Button LED light entities for Wiser by Feller."""

from __future__ import annotations

from typing import Any

from aiowiserbyfeller import Device, Load
from aiowiserbyfeller.enum import BlinkPattern
from homeassistant.components.light import (
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.components.light.const import ColorMode
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, MANUFACTURER
from .coordinator import WiserCoordinator

LED_EFFECTS = [pattern.value for pattern in BlinkPattern]


def rgb_tuple_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def get_device_name(device: Device | None, device_id: str) -> str:
    """Return readable Wiser device name."""
    if device is None:
        return device_id

    if getattr(device, "c_name", None):
        return device.c_name

    if getattr(device, "a_name", None):
        return device.a_name

    return device_id


def get_layout(device_buttons: list[dict]) -> str:
    """Return button layout for a Wiser device."""
    channels = sorted({int(button["channel"]) for button in device_buttons})
    sub_types = {button.get("sub_type") for button in device_buttons}

    if len(channels) == 4 and sub_types == {"scene"}:
        return "four_scene"

    if len(channels) == 1 and sub_types == {"up down"}:
        return "single_up_down"

    if len(channels) == 2 and sub_types == {"up down"}:
        return "up_down"

    return "default"


def get_up_down_button_id(device_buttons: list[dict]) -> int | None:
    """Return fallback button id for pure up/down layouts."""
    for button in device_buttons:
        if button.get("id") is not None:
            return int(button["id"])

    return None


def get_first_load_for_device(
    device_id: str,
    loads_by_device_channel: dict[tuple[str, int], Load],
) -> Load | None:
    """Return first load assigned to a physical Wiser device."""
    loads = [
        load
        for (load_device_id, _channel), load in loads_by_device_channel.items()
        if load_device_id == device_id
    ]

    if not loads:
        return None

    return sorted(loads, key=lambda load: load.channel)[0]


def build_led_definitions(device_buttons: list[dict]) -> list[dict]:
    """Build LED definitions for all buttons of one device."""
    layout = get_layout(device_buttons)
    definitions: list[dict] = []
    scene_counter = 1

    for button in sorted(device_buttons, key=lambda item: int(item["channel"])):
        channel = int(button["channel"])
        sub_type = button.get("sub_type")

        if layout == "four_scene":
            if sub_type != "scene" or button.get("id") is None:
                continue

            position = {
                0: "links oben",
                1: "links unten",
                2: "rechts oben",
                3: "rechts unten",
            }.get(channel, f"Kanal {channel}")

            definitions.append(
                {
                    "button_id": int(button["id"]),
                    "led_index": 0,
                    "channel": channel,
                    "position": position,
                    "load_channel": None,
                    "sub_type": sub_type,
                }
            )
            continue

        if layout == "single_up_down":
            button_id = get_up_down_button_id(device_buttons)
            if button_id is None:
                continue

            definitions.extend(
                [
                    {
                        "button_id": button_id,
                        "led_index": 0,
                        "channel": channel,
                        "position": "oben",
                        "load_channel": channel,
                        "sub_type": sub_type,
                    },
                    {
                        "button_id": button_id,
                        "led_index": 1,
                        "channel": channel,
                        "position": "unten",
                        "load_channel": channel,
                        "sub_type": sub_type,
                    },
                ]
            )
            continue

        if layout == "up_down":
            button_id = get_up_down_button_id(device_buttons)
            if button_id is None:
                continue

            definitions.append(
                {
                    "button_id": button_id,
                    "led_index": 0 if channel == 0 else 1,
                    "channel": channel,
                    "position": "oben" if channel == 0 else "unten",
                    "load_channel": 0,
                    "sub_type": sub_type,
                }
            )
            continue

        if sub_type == "scene":
            if button.get("id") is None:
                continue

            definitions.append(
                {
                    "button_id": int(button["id"]),
                    "led_index": 0,
                    "channel": channel,
                    "position": f"Szene {scene_counter}",
                    "load_channel": None,
                    "sub_type": sub_type,
                }
            )
            scene_counter += 1
            continue

        if button.get("id") is None:
            continue

        definitions.append(
            {
                "button_id": int(button["id"]),
                "led_index": 0,
                "channel": channel,
                "position": "",
                "load_channel": channel,
                "sub_type": sub_type,
            }
        )

    return definitions


def create_button_led_entities(coordinator: WiserCoordinator) -> list[WiserButtonLedLightEntity]:
    """Create one HA light entity per controllable button LED."""
    entities: list[WiserButtonLedLightEntity] = []

    for device_id, device_buttons in coordinator.buttons_by_device.items():
        device = coordinator.devices.get(device_id) if coordinator.devices else None
        fallback_load = get_first_load_for_device(
            device_id,
            coordinator.loads_by_device_channel,
        )

        for led_definition in build_led_definitions(device_buttons):
            load = None
            room = None

            load_channel = led_definition["load_channel"]
            if load_channel is not None:
                load = coordinator.loads_by_device_channel.get((device_id, load_channel))

            if load is None and led_definition["sub_type"] != "scene":
                load = fallback_load

            if load is not None:
                room = (
                    coordinator.rooms.get(load.room)
                    if load.room is not None and coordinator.rooms
                    else None
                )
            elif led_definition["sub_type"] == "scene" and fallback_load is not None:
                room = (
                    coordinator.rooms.get(fallback_load.room)
                    if fallback_load.room is not None and coordinator.rooms
                    else None
                )

            entities.append(
                WiserButtonLedLightEntity(
                    coordinator=coordinator,
                    device_id=device_id,
                    device=device,
                    load=load,
                    room=room,
                    button_id=led_definition["button_id"],
                    led_index=led_definition["led_index"],
                    channel=led_definition["channel"],
                    position=led_definition["position"],
                    sub_type=led_definition["sub_type"],
                )
            )

    return entities


class WiserButtonLedLightEntity(LightEntity):
    """Wiser button LED exposed as a Home Assistant light."""

    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = LED_EFFECTS
    _attr_icon = "mdi:button-pointer"

    def __init__(
        self,
        coordinator: WiserCoordinator,
        device_id: str,
        device: Device | None,
        load: Load | None,
        room: dict | None,
        button_id: int,
        led_index: int,
        channel: int,
        position: str,
        sub_type: str | None,
    ) -> None:
        """Initialize button LED light."""
        self.coordinator = coordinator
        self._device_id = device_id
        self._device = device
        self._load = load
        self._room = room
        self._button_id = button_id
        self._led_index = led_index
        self._channel = channel
        self._position = position
        self._sub_type = sub_type

        self._attr_unique_id = f"{device_id}_led_channel_{channel}_index_{led_index}"
        self._attr_is_on = False
        self._attr_rgb_color = (0, 255, 0)
        self._attr_effect = BlinkPattern.PERMANENT.value

        if self._sub_type == "scene":
            base_name = "LED"
        elif self._load is not None:
            base_name = f"{self._load.name} LED"
        else:
            base_name = f"{get_device_name(self._device, self._device_id)} LED"

        self._attr_name = f"{base_name} {self._position}" if self._position else base_name

    @property
    def device_info(self) -> DeviceInfo | None:
        """Attach LED entity to the correct HA device."""
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
            f"{self._device.c['fw_version']} (Controls) / "
            f"{self._device.a['fw_version']} (Actuator)"
            if self._device.c["fw_version"] != self._device.a["fw_version"]
            else self._device.a["fw_version"]
        )

        if self._load is not None:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{self._load.device}_{self._load.channel}")},
                name=self._load.name,
                manufacturer=MANUFACTURER,
                model=model,
                model_id=model_id,
                sw_version=firmware,
                serial_number=self._device.combined_serial_number,
                suggested_area=None if self._room is None else self._room["name"],
                via_device=(
                    (DOMAIN, self.coordinator.gateway.combined_serial_number)
                    if self.coordinator.gateway is not None
                    else None
                ),
            )

        if self._sub_type == "scene":
            if self._room is not None:
                device_name = f"Szenetaster {self._room['name']}"
            else:
                device_name = f"Szenetaster Device {self._device_id[-4:]}"
        else:
            device_name = get_device_name(self._device, self._device_id)

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=model,
            model_id=model_id,
            sw_version=firmware,
            serial_number=self._device.combined_serial_number,
            suggested_area=None if self._room is None else self._room["name"],
            via_device=(
                (DOMAIN, self.coordinator.gateway.combined_serial_number)
                if self.coordinator.gateway is not None
                else None
            ),
        )

    @property
    def is_on(self) -> bool:
        """Return LED override state."""
        return self._attr_is_on

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return current RGB color."""
        return self._attr_rgb_color

    @property
    def effect(self) -> str:
        """Return current LED effect."""
        return self._attr_effect

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn LED override on."""
        rgb_color = tuple(kwargs.get(ATTR_RGB_COLOR, self._attr_rgb_color))
        effect = kwargs.get(ATTR_EFFECT, self._attr_effect or BlinkPattern.PERMANENT.value)

        try:
            pattern = BlinkPattern(effect)
        except ValueError:
            pattern = BlinkPattern.PERMANENT
            effect = pattern.value

        await self.coordinator.api.async_set_button_led(
            button_id=self._button_id,
            led_index=self._led_index,
            on=True,
            pattern=pattern,
            color=rgb_tuple_to_hex(rgb_color),
        )

        self._attr_is_on = True
        self._attr_rgb_color = rgb_color
        self._attr_effect = effect
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn LED override off."""
        try:
            pattern = BlinkPattern(self._attr_effect or BlinkPattern.PERMANENT.value)
        except ValueError:
            pattern = BlinkPattern.PERMANENT

        await self.coordinator.api.async_set_button_led(
            button_id=self._button_id,
            led_index=self._led_index,
            on=False,
            pattern=pattern,
            color=rgb_tuple_to_hex(self._attr_rgb_color),
        )

        self._attr_is_on = False
        self.async_write_ha_state()
