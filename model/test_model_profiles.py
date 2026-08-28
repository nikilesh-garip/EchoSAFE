"""Tests for the two-head model profile registry.

Imports no TensorFlow: the taxonomy contract is what keeps a demo detection
from being recorded as a real one, and it should be checkable instantly.
"""

import csv
import os

import pytest

from audio_classes import CLASS_MAPPING, DEMO_CLASS_MAPPING
from data_manifest import validate_manifest
from model_profiles import (
    DEMO_PROFILE,
    REAL_PROFILE,
    available_profiles,
    get_profile,
)


def test_production_taxonomy_has_no_firecracker_class():
    # The whole point of the split: a firecracker must never be a trainable
    # target of the head that runs in a real emergency.
    assert "firecracker" not in CLASS_MAPPING
    assert "firecracker" not in REAL_PROFILE.class_mapping
    assert REAL_PROFILE.num_classes == 8


def test_demo_profile_extends_the_production_taxonomy_without_reordering_it():
    # Index stability matters: if the demo head reindexed the shared classes,
    # every comparison between the two heads' outputs would be meaningless.
    for name, index in CLASS_MAPPING.items():
        assert DEMO_CLASS_MAPPING[name] == index
    assert DEMO_PROFILE.class_mapping["firecracker"] == 8
    assert DEMO_PROFILE.num_classes == 9


def test_demo_profile_aliases_firecracker_to_gunshot_only():
    assert DEMO_PROFILE.resolve_class("firecracker") == "gunshot"
    assert DEMO_PROFILE.resolve_class("scream") == "scream"
    assert REAL_PROFILE.resolve_class("gunshot") == "gunshot"
    # The production profile has no aliases at all.
    assert REAL_PROFILE.alias_map == {}


def test_profiles_use_separate_checkpoints_and_manifests():
    assert REAL_PROFILE.checkpoint_path != DEMO_PROFILE.checkpoint_path
    assert REAL_PROFILE.manifest_path != DEMO_PROFILE.manifest_path


def test_unknown_profile_fails_loudly():
    with pytest.raises(ValueError):
        get_profile("production")


def test_demo_profile_carries_a_visible_banner():
    assert "DEMO" in DEMO_PROFILE.banner.upper()
    names = {entry["name"] for entry in available_profiles()}
    assert names == {"real", "demo"}


def _write_manifest(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filepath", "label", "source_dataset", "source_clip_id", "split"]
        )
        writer.writeheader()
        writer.writerows(rows)


def _rows_for(classes):
    rows = []
    for label in classes:
        for split in ("train", "validation", "test"):
            rows.append({
                "filepath": "/tmp/{}_{}.wav".format(label, split),
                "label": label,
                "source_dataset": "test_fixture",
                "source_clip_id": "{}_{}".format(label, split),
                "split": split,
            })
    return rows


def test_manifest_validator_accepts_the_demo_taxonomy(tmp_path):
    manifest = os.path.join(tmp_path, "metadata.csv")
    _write_manifest(manifest, _rows_for(DEMO_CLASS_MAPPING))
    result = validate_manifest(manifest, target_classes=set(DEMO_CLASS_MAPPING))
    assert result["valid"], result["blockers"]


def test_firecracker_rows_are_rejected_by_the_production_contract(tmp_path):
    manifest = os.path.join(tmp_path, "metadata.csv")
    _write_manifest(manifest, _rows_for(DEMO_CLASS_MAPPING))
    result = validate_manifest(manifest)  # default = production taxonomy
    assert not result["valid"]
    assert any("firecracker" in blocker for blocker in result["blockers"])


def test_demo_manifest_missing_firecracker_is_rejected(tmp_path):
    manifest = os.path.join(tmp_path, "metadata.csv")
    _write_manifest(manifest, _rows_for(CLASS_MAPPING))
    result = validate_manifest(manifest, target_classes=set(DEMO_CLASS_MAPPING))
    assert not result["valid"]
    assert any("firecracker" in blocker for blocker in result["blockers"])
