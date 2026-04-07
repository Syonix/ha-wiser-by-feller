"""Various utility methods."""

from aiowiserbyfeller import Device, Load


def resolve_load_channel_name(device: Device, pos: int) -> str:
    """Get the button position string of a device load."""
    buttons = len(device.outputs)

    if buttons < 2:
        return ""

    ref = device.c["comm_ref"]

    if ref == "3400.2.VS":
        values_map = ["Top", "Bottom"]
    elif buttons == 2:
        values_map = ["Left", "Right"]
    else:
        values_map = ["Top Left", "Bottom Left", "Top Right", "Bottom Right"]

    return " " + values_map[pos]


def resolve_load_name(load: Load, room: dict):
    """Get the name of a load."""
    if room is None or room["name"] in load.name:
        return load.name

    return f"{room['name']} {load.name}"


def resolve_device_name(device: Device, room: dict | None, load: Load | None) -> str:
    """Get the name of a device."""
    if load is not None:
        name = load.name
    else:
        name_c = device.c["comm_name"]
        name_a = device.a["comm_name"]
        name = name_c if name_a in name_c else f"{name_c} ({name_a})"

    if room is None or room["name"] in name:
        return name

    return f"{room['name']} {name}"


def wiser_to_brightness(value: int | None) -> int | None:
    """Convert a Wiser brightness value (0..10000) to a HA brightness value (0..255)."""
    if value is None:
        return None
    return int(value / 10000 * 255)


def brightness_to_wiser(brightness: int) -> int:
    """Convert a HA brightness value (0..255) to a Wiser brightness value (0..10000)."""
    return int(brightness / 255 * 10000)


def wiser_to_cover_position(value: int | None) -> int | None:
    """Convert a Wiser cover position (0..10000) to a HA cover position (100..0)."""
    if value is None:
        return None
    return 100 - int(value / 100)


def cover_position_to_wiser(cover_position: int) -> int:
    """Convert a HA cover position (100..0) to a Wiser cover position (0..10000)."""
    return (100 - cover_position) * 100


def wiser_to_cover_tilt(value: int | None) -> int | None:
    """Convert a Wiser cover tilt (0..9) to a HA cover tilt (0..100)."""
    if value is None:
        return None
    return int(value / 9 * 100)


def cover_tilt_to_wiser(cover_position: int) -> int:
    """Convert a HA cover tilt (0..100) to a Wiser cover tilt (0..9)."""
    return int(cover_position / 100 * 9)


def hex_to_rbg_tuple(hexval: str) -> tuple[int, ...]:
    """Convert a hex color code to an RGB tuple."""
    color = hexval.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def rgb_tuple_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB color tuple to a hex color code."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)
