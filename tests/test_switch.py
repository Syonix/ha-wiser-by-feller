"""Tests for switch platform entities (WiserSystemFlag, WiserOnOffSwitchEntity)."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import OnOff, SystemFlag
from aiowiserbyfeller.const import KIND_LIGHT, KIND_SWITCH
from homeassistant.helpers import entity_registry as er

from custom_components.wiser_by_feller.const import DOMAIN
from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.switch import WiserSystemFlag

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_flag(flag_id=1, name="Party Mode", value=False, symbol=None):
    flag = MagicMock(spec=SystemFlag)
    flag.id = flag_id
    flag.name = name
    flag.value = value
    flag.symbol = symbol or f"flag_{flag_id}"
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


def _make_onoff_load(load_id=1, kind=KIND_SWITCH, device_id="0002244a"):
    load = MagicMock(spec=OnOff)
    load.id = load_id
    load.name = "Linke Glühbirne"
    load.device = device_id
    load.room = None
    load.kind = kind
    load.type = "onoff"
    load.sub_type = ""
    load.unused = False
    load.state = False
    load.raw_state = {"bri": 0}
    load.async_switch_on = AsyncMock()
    load.async_switch_off = AsyncMock()
    return load


def _make_switch_device(device_id="0002244a"):
    device = MagicMock()
    device.id = device_id
    device.c = {
        "comm_ref": "3406.4.S.A.F",
        "comm_name": "Druckschalter",
        "fw_version": "0x00500a28",
    }
    device.a = {
        "comm_ref": "3406.4.S.A.F",
        "comm_name": "Druckschalter",
        "fw_version": "0x00500a28",
    }
    device.c_name = "Druckschalter"
    device.a_name = "Druckschalter"
    device.combined_serial_number = "011110_B_000064"
    device.outputs = [{"load": 1}]
    return device


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
    assert len(switch_states) == 2


async def test_switch_platform_creates_onoff_switch_entity(
    hass, mock_config_entry, mock_coordinator
):
    """Platform setup creates a WiserOnOffSwitchEntity for OnOff loads with kind==KIND_SWITCH."""
    load = _make_onoff_load()
    device = _make_switch_device()

    mock_coordinator.loads = {load.id: load}
    mock_coordinator.states = {load.id: {"bri": 0}}
    mock_coordinator.devices = {load.device: device}
    mock_coordinator.rooms = {}
    mock_coordinator.system_flags = []

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
    assert len(switch_states) == 1


async def test_kind_light_onoff_load_not_in_switch_platform(
    hass, mock_config_entry, mock_coordinator
):
    """OnOff loads with kind==KIND_LIGHT must not appear in the switch platform."""
    load = _make_onoff_load(kind=KIND_LIGHT)
    device = _make_switch_device()

    mock_coordinator.loads = {load.id: load}
    mock_coordinator.states = {load.id: {"bri": 0}}
    mock_coordinator.devices = {load.device: device}
    mock_coordinator.rooms = {}
    mock_coordinator.system_flags = []

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
    assert len(switch_states) == 0


# ── re-resolution on coordinator update ───────────────────────────────────────


def test_handle_coordinator_update_re_resolves_flag():
    """A re-polled flag object with the same id replaces the stale reference."""
    coord = _make_coordinator()
    entity = WiserSystemFlag(coord, _make_flag(flag_id=3, value=False, name="Old"))
    entity.async_write_ha_state = MagicMock()

    coord.system_flags = [_make_flag(flag_id=3, value=True, name="New")]
    entity._handle_coordinator_update()

    assert entity.is_on is True
    assert entity._attr_name == "New"


def test_handle_coordinator_update_clears_name_when_unnamed():
    """A flag renamed to no name falls back to the translation key."""
    coord = _make_coordinator()
    entity = WiserSystemFlag(coord, _make_flag(flag_id=3, name="Old"))
    entity.async_write_ha_state = MagicMock()

    coord.system_flags = [_make_flag(flag_id=3, name=None)]
    entity._handle_coordinator_update()

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "unnamed_flag"


def test_handle_coordinator_update_keeps_flag_when_vanished():
    """When the flag disappeared from the cache, the last object is kept."""
    coord = _make_coordinator()
    entity = WiserSystemFlag(coord, _make_flag(flag_id=3, value=True))
    entity.async_write_ha_state = MagicMock()

    coord.system_flags = []
    entity._handle_coordinator_update()

    assert entity.is_on is True


def test_extra_state_attributes_expose_flag_id_and_symbol():
    """Flag id and symbol are exposed for use in Wiser jobs and conditions."""
    entity = WiserSystemFlag(
        _make_coordinator(), _make_flag(flag_id=3, symbol="holiday")
    )
    assert entity.extra_state_attributes == {"flag_id": 3, "symbol": "holiday"}


# ── dynamic add / remove ──────────────────────────────────────────────────────


def _get_flag_sync_listener(mock_coordinator):
    """Return the switch platform's flag sync callback from the coordinator mock."""
    for call in mock_coordinator.async_add_listener.call_args_list:
        listener = call.args[0]
        if getattr(listener, "__name__", "") == "_sync_system_flag_entities":
            return listener
    raise AssertionError("flag sync listener not registered")


async def test_switch_platform_adds_new_flag_dynamically(
    hass, mock_config_entry, mock_coordinator
):
    """A flag appearing after setup creates its switch entity without a reload."""
    flag1 = _make_flag(flag_id=1, name="Flag One")
    mock_coordinator.system_flags = [flag1]

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

    assert len(hass.states.async_entity_ids("switch")) == 1

    mock_coordinator.system_flags = [flag1, _make_flag(flag_id=2, name="Flag Two")]
    _get_flag_sync_listener(mock_coordinator)()
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("switch")) == 2


async def test_switch_platform_removes_deleted_flag_dynamically(
    hass, mock_config_entry, mock_coordinator
):
    """A flag deleted after setup removes its entity from the registry."""
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

    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, "20012161_flag_2")

    mock_coordinator.system_flags = [flag1]
    _get_flag_sync_listener(mock_coordinator)()
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("switch", DOMAIN, "20012161_flag_2") is None
    assert registry.async_get_entity_id("switch", DOMAIN, "20012161_flag_1")
    assert len(hass.states.async_entity_ids("switch")) == 1
