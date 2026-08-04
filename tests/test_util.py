"""Tests for utility functions."""

from unittest.mock import MagicMock

from custom_components.wiser_by_feller.util import (
    brightness_to_wiser,
    cover_position_to_wiser,
    cover_tilt_to_wiser,
    format_button_inputs,
    hex_to_rbg_tuple,
    resolve_button_inputs,
    resolve_device_name,
    rgb_tuple_to_hex,
    wiser_to_brightness,
    wiser_to_cover_position,
    wiser_to_cover_tilt,
)


def test_brightness_wiser_to_ha_boundaries():
    """Wiser 0 → HA 0; Wiser 10000 → HA 255."""
    assert wiser_to_brightness(0) == 0
    assert wiser_to_brightness(10000) == 255


def test_brightness_ha_to_wiser_boundaries():
    """HA 0 → Wiser 0; HA 255 → Wiser 10000."""
    assert brightness_to_wiser(0) == 0
    assert brightness_to_wiser(255) == 10000


def test_brightness_round_trip():
    """Round-trip conversion preserves value at boundary points."""
    for ha_val in (0, 127, 255):
        assert abs(wiser_to_brightness(brightness_to_wiser(ha_val)) - ha_val) <= 1


def test_brightness_none():
    """None input returns None without error."""
    assert wiser_to_brightness(None) is None


def test_cover_position_inverts():
    """Wiser 0 (fully open) → HA 100; Wiser 10000 (fully closed) → HA 0."""
    # Wiser 0 → fully open → HA 100; Wiser 10000 → fully closed → HA 0
    assert wiser_to_cover_position(0) == 100
    assert wiser_to_cover_position(10000) == 0


def test_cover_position_round_trip():
    """Round-trip cover position conversion preserves value at key points."""
    for ha_val in (0, 50, 100):
        assert wiser_to_cover_position(cover_position_to_wiser(ha_val)) == ha_val


def test_cover_position_none():
    """None cover position returns None without error."""
    assert wiser_to_cover_position(None) is None


def test_cover_tilt_round_trip():
    """Round-trip tilt conversion preserves value at boundary points 0 and 100."""
    # cover_tilt_to_wiser uses int(ha/100*9) → only 0 and 100 survive losslessly
    for ha_val in (0, 100):
        result = wiser_to_cover_tilt(cover_tilt_to_wiser(ha_val))
        assert result == ha_val


def test_cover_tilt_none():
    """None tilt input returns None without error."""
    assert wiser_to_cover_tilt(None) is None


def test_hex_to_rgb_tuple():
    """Hex color string is correctly parsed into an RGB tuple."""
    assert hex_to_rbg_tuple("#ff0000") == (255, 0, 0)
    assert hex_to_rbg_tuple("#1abcf2") == (0x1A, 0xBC, 0xF2)


def test_rgb_tuple_to_hex():
    """RGB tuple is correctly formatted as a lowercase hex color string."""
    assert rgb_tuple_to_hex((255, 0, 0)) == "#ff0000"
    assert rgb_tuple_to_hex((0, 0, 0)) == "#000000"


def test_hex_rgb_round_trip():
    """Hex → RGB → Hex round-trip preserves the original tuple."""
    original = (0x1A, 0xBC, 0xF2)
    assert hex_to_rbg_tuple(rgb_tuple_to_hex(original)) == original


def test_resolve_device_name_with_room():
    """Device name includes the room name when a room is provided."""
    device = _make_device("Living Room Dimmer", "Dimmer")
    room = {"name": "Living Room"}
    result = resolve_device_name(device, room, None)
    assert "Living Room" in result


def test_resolve_device_name_no_room():
    """Device name is a non-empty string when no room is provided."""
    device = _make_device("Dimmer", "Dimmer")
    result = resolve_device_name(device, None, None)
    assert result  # just some non-empty string


def test_resolve_device_name_room_already_in_name():
    """Room name is not duplicated when it is already present in the device name."""
    device = _make_device("Bedroom Light", "Light")
    room = {"name": "Bedroom"}
    result = resolve_device_name(device, room, None)
    # Room name already in device name — should not duplicate
    assert result.count("Bedroom") == 1


def test_resolve_device_name_self_describing_front():
    """Touch display fronts omit the actuator module name."""
    device = _make_device(
        "Touch Thermostat", "Thermostat Nebenstelle", fw_id_c="0x9200"
    )
    assert resolve_device_name(device, None, None) == "Touch Thermostat"


def test_resolve_device_name_standard_front_keeps_actuator_name():
    """Push button fronts keep the combined name format."""
    device = _make_device("Druckschalter 1K", "LED-Universaldimmer", fw_id_c="0x8402")
    result = resolve_device_name(device, None, None)
    assert result == "Druckschalter 1K (LED-Universaldimmer)"


def test_resolve_device_name_self_describing_front_empty_c_name():
    """An empty front name falls back to the combined name format."""
    device = _make_device("", "Thermostat Nebenstelle", fw_id_c="0x9200")
    assert "Thermostat Nebenstelle" in resolve_device_name(device, None, None)


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_device(comm_name_c: str, comm_name_a: str, fw_id_c: str = ""):
    device = MagicMock()
    device.c = {
        "comm_name": comm_name_c,
        "comm_ref": "ABC",
        "fw_version": "1.0",
        "fw_id": fw_id_c,
    }
    device.a = {"comm_name": comm_name_a, "comm_ref": "ABC", "fw_version": "1.0"}
    device.c_name = comm_name_c
    device.a_name = comm_name_a
    return device


# ── resolve_button_inputs ────────────────────────────────────────────────────
#
# The input shapes below are taken verbatim from real device diagnostics.


def _make_device_with_inputs(*inputs):
    device = MagicMock()
    device.inputs = list(inputs)
    return device


def _button(sub_type: str, button_id: int | None = None) -> dict:
    entry = {"type": "button", "sub_type": sub_type}
    if button_id is not None:
        entry["button"] = button_id
    return entry


def test_resolve_button_inputs_single_rocker():
    """A one-rocker front (dimmer, blind) reports a single positionless button."""
    device = _make_device_with_inputs(_button("up down"))
    assert resolve_button_inputs(device) == {
        0: {"sub_type": "up down", "position": "single", "button_id": None}
    }


def test_resolve_button_inputs_two_gang():
    """A two-gang front is numbered left, right."""
    device = _make_device_with_inputs(_button("toggle"), _button("toggle"))
    result = resolve_button_inputs(device)
    assert [info["position"] for info in result.values()] == ["left", "right"]


def test_resolve_button_inputs_rocker_plus_two_scenes():
    """A dimmer with two scene buttons: rocker left, scenes top/bottom right."""
    device = _make_device_with_inputs(
        _button("up down"), _button("scene", 70), _button("scene", 74)
    )
    assert resolve_button_inputs(device) == {
        0: {"sub_type": "up down", "position": "left", "button_id": None},
        1: {"sub_type": "scene", "position": "top_right", "button_id": 70},
        2: {"sub_type": "scene", "position": "bottom_right", "button_id": 74},
    }


def test_resolve_button_inputs_four_scenes():
    """A four-scene front is numbered top left, bottom left, top right, bottom right."""
    device = _make_device_with_inputs(*[_button("scene") for _ in range(4)])
    assert [info["position"] for info in resolve_button_inputs(device).values()] == [
        "top_left",
        "bottom_left",
        "top_right",
        "bottom_right",
    ]


def test_resolve_button_inputs_skips_sensor_inputs():
    """Sensor inputs of a room sensor are not selectable channels."""
    device = _make_device_with_inputs(
        _button("touch_display"),
        {"type": "temperature", "sub_type": ""},
        {"type": "humidity", "sub_type": ""},
        {"type": "CO2", "sub_type": ""},
        {"type": "temperature", "sub_type": "ntc"},
        {"type": "window", "sub_type": ""},
    )
    result = resolve_button_inputs(device)
    assert list(result) == [0]
    assert result[0]["sub_type"] == "touch_display"


def test_resolve_button_inputs_keeps_channel_numbering():
    """Channels stay the raw input index, even when sensors sit in between."""
    device = _make_device_with_inputs(
        {"type": "temperature", "sub_type": ""},
        _button("scene"),
    )
    assert list(resolve_button_inputs(device)) == [1]


def test_resolve_button_inputs_unknown_count_has_no_position():
    """A front with an unmapped number of buttons reports no position."""
    device = _make_device_with_inputs(*[_button("scene") for _ in range(5)])
    assert all(
        info["position"] is None for info in resolve_button_inputs(device).values()
    )


def test_format_button_inputs():
    """Channels are formatted with their sub type for error messages."""
    device = _make_device_with_inputs(_button("up down"), _button("scene"))
    assert (
        format_button_inputs(resolve_button_inputs(device)) == "0 (up down), 1 (scene)"
    )
