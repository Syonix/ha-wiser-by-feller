"""Tests for switch platform entities (WiserSystemFlag)."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import SystemFlag

from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.switch import WiserSystemFlag

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_flag(flag_id=1, name="Party Mode", value=False):
    flag = MagicMock(spec=SystemFlag)
    flag.id = flag_id
    flag.name = name
    flag.value = value
    flag.async_enable = AsyncMock()
    flag.async_disable = AsyncMock()
    flag.async_toggle = AsyncMock()
    return flag


def _make_coordinator(gateway_sn="20012161"):
    coord = MagicMock(spec=WiserCoordinator)
    gw = MagicMock()
    gw.combined_serial_number = gateway_sn
    coord.gateway = gw
    coord.config_entry = MagicMock()
    coord.config_entry.title = "Test Wiser"
    return coord


# ── is_on ─────────────────────────────────────────────────────────────────────


def test_is_on_true():
    """Flag with value True → is_on is True."""
    flag = _make_flag(value=True)
    entity = WiserSystemFlag(_make_coordinator(), flag)
    assert entity.is_on is True


def test_is_on_false():
    """Flag with value False → is_on is False."""
    flag = _make_flag(value=False)
    entity = WiserSystemFlag(_make_coordinator(), flag)
    assert entity.is_on is False


# ── turn_on / turn_off / toggle ───────────────────────────────────────────────


async def test_turn_on_calls_async_enable():
    """async_turn_on calls flag.async_enable()."""
    flag = _make_flag()
    entity = WiserSystemFlag(_make_coordinator(), flag)
    entity.async_write_ha_state = MagicMock()
    await entity.async_turn_on()
    flag.async_enable.assert_called_once()


async def test_turn_off_calls_async_disable():
    """async_turn_off calls flag.async_disable()."""
    flag = _make_flag(value=True)
    entity = WiserSystemFlag(_make_coordinator(), flag)
    entity.async_write_ha_state = MagicMock()
    await entity.async_turn_off()
    flag.async_disable.assert_called_once()


async def test_toggle_calls_async_toggle():
    """async_toggle calls flag.async_toggle()."""
    flag = _make_flag()
    entity = WiserSystemFlag(_make_coordinator(), flag)
    entity.async_write_ha_state = MagicMock()
    await entity.async_toggle()
    flag.async_toggle.assert_called_once()


# ── unique_id ─────────────────────────────────────────────────────────────────


def test_unique_id_contains_gateway_sn():
    """Unique ID includes both the gateway serial number and flag ID."""
    coord = _make_coordinator(gateway_sn="GW_SERIAL_001")
    flag = _make_flag(flag_id=3)
    entity = WiserSystemFlag(coord, flag)
    assert "GW_SERIAL_001" in entity.unique_id
    assert "3" in entity.unique_id


def test_unique_id_uses_title_when_no_gateway():
    """Unique ID falls back to config entry title when gateway is None."""
    coord = _make_coordinator()
    coord.gateway = None
    flag = _make_flag(flag_id=1)
    entity = WiserSystemFlag(coord, flag)
    assert "Test Wiser" in entity.unique_id


# ── entity name ───────────────────────────────────────────────────────────────


def test_entity_name_matches_flag_name():
    """Entity name matches the system flag name from the API."""
    flag = _make_flag(name="Vacation Mode")
    entity = WiserSystemFlag(_make_coordinator(), flag)
    assert entity.name == "Vacation Mode"


# ── platform setup creates one entity per flag ────────────────────────────────


async def test_switch_platform_creates_one_entity_per_flag(
    hass, mock_config_entry, mock_coordinator
):
    """Platform setup creates exactly one WiserSystemFlag entity per system flag."""
    flag1 = _make_flag(flag_id=1, name="Flag One")
    flag2 = _make_flag(flag_id=2, name="Flag Two")
    mock_coordinator.system_flags = [flag1, flag2]

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

    switch_states = hass.states.async_entity_ids("switch")
    # Filter out OnOffSwitch entities from light.py — only system flags expected here
    # (in this test there are no loads, so all switches are flags)
    assert len(switch_states) == 2
