"""Tests for scene platform entities."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiowiserbyfeller import Scene

from custom_components.wiser_by_feller.coordinator import WiserCoordinator
from custom_components.wiser_by_feller.scene import WiserSceneEntity

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_scene(scene_id=1, name="Movie Night", job_id=100):
    scene = MagicMock(spec=Scene)
    scene.id = scene_id
    scene.name = name
    scene.job = job_id
    scene.raw_data = {"id": scene_id, "name": name}
    return scene


def _make_job(job_id=100):
    job = MagicMock()
    job.id = job_id
    job.async_trigger_all = AsyncMock()
    return job


def _make_coordinator(gateway_sn="20012161", scenes=None, jobs=None):
    coord = MagicMock(spec=WiserCoordinator)
    gw = MagicMock()
    gw.combined_serial_number = gateway_sn
    coord.gateway = gw
    coord.config_entry = MagicMock()
    coord.config_entry.title = "Test Wiser"
    coord.scenes = scenes or {}
    coord.jobs = jobs or {}
    return coord


# ── WiserSceneEntity ──────────────────────────────────────────────────────────


def test_scene_entity_name():
    """Scene entity name matches the scene name from the API."""
    scene = _make_scene(name="Dinner Party")
    coord = _make_coordinator(jobs={100: _make_job()})
    entity = WiserSceneEntity(coord, scene)
    assert entity.name == "Dinner Party"


def test_scene_unique_id_contains_gateway_sn_and_scene_id():
    """Unique ID includes both the gateway serial number and the scene ID."""
    scene = _make_scene(scene_id=5)
    coord = _make_coordinator(gateway_sn="GW_ABC")
    entity = WiserSceneEntity(coord, scene)
    assert "GW_ABC" in entity.unique_id
    assert "5" in entity.unique_id


def test_scene_unique_id_uses_title_when_no_gateway():
    """Unique ID falls back to config entry title when gateway is None."""
    scene = _make_scene(scene_id=5)
    coord = _make_coordinator()
    coord.gateway = None
    entity = WiserSceneEntity(coord, scene)
    assert "Test Wiser" in entity.unique_id


async def test_activate_calls_job_async_trigger_all():
    """async_activate triggers the associated job via async_trigger_all."""
    job = _make_job(job_id=100)
    scene = _make_scene(job_id=100)
    coord = _make_coordinator(jobs={100: job})
    entity = WiserSceneEntity(coord, scene)
    await entity.async_activate()
    job.async_trigger_all.assert_called_once()


# ── setup: scenes without jobs are skipped ────────────────────────────────────


async def test_scenes_without_jobs_excluded(hass, mock_config_entry, mock_coordinator):
    """Scenes whose job ID is not in coordinator.jobs are not created as entities."""
    scene_with_job = _make_scene(scene_id=1, job_id=100)
    scene_without_job = _make_scene(scene_id=2, job_id=999)  # job 999 not in jobs
    job = _make_job(job_id=100)

    mock_coordinator.scenes = {1: scene_with_job, 2: scene_without_job}
    mock_coordinator.jobs = {100: job}  # only job 100

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

    scene_states = hass.states.async_entity_ids("scene")
    assert len(scene_states) == 1


async def test_all_scenes_with_jobs_created(hass, mock_config_entry, mock_coordinator):
    """One scene entity is created for each scene that has a corresponding job."""
    scenes = {i: _make_scene(scene_id=i, job_id=i + 100) for i in range(1, 4)}
    jobs = {i + 100: _make_job(job_id=i + 100) for i in range(1, 4)}

    mock_coordinator.scenes = scenes
    mock_coordinator.jobs = jobs

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

    scene_states = hass.states.async_entity_ids("scene")
    assert len(scene_states) == 3
