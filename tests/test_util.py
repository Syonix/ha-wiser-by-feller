"""Tests for utility functions."""

from unittest.mock import MagicMock

from custom_components.wiser_by_feller.util import (
    brightness_to_wiser,
    cover_position_to_wiser,
    cover_tilt_to_wiser,
    hex_to_rbg_tuple,
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_device(comm_name_c: str, comm_name_a: str):
    device = MagicMock()
    device.c = {"comm_name": comm_name_c, "comm_ref": "ABC", "fw_version": "1.0"}
    device.a = {"comm_name": comm_name_a, "comm_ref": "ABC", "fw_version": "1.0"}
    device.c_name = comm_name_c
    device.a_name = comm_name_a
    return device
