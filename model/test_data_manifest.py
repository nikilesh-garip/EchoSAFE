import csv
import tempfile
from pathlib import Path

from data_manifest import TARGET_CLASSES, validate_manifest


def write_manifest(path, rows):
    with path.open("w", newline="", encoding="utf-8") as manifest:
        writer = csv.DictWriter(
            manifest,
            fieldnames=["filepath", "label", "source_dataset", "source_clip_id", "split"],
        )
        writer.writeheader()
        writer.writerows(rows)


def complete_rows():
    # Every class needs at least one example in every split, not just one row
    # total, otherwise a manifest can be "complete" by the old, weaker
    # definition while still handing train.py a class with zero test examples.
    splits = ("train", "validation", "test")
    return [
        {
            "filepath": f"/audio/{label}_{split}.wav",
            "label": label,
            "source_dataset": "field_test",
            "source_clip_id": f"source-{label}-{split}",
            "split": split,
        }
        for label in sorted(TARGET_CLASSES)
        for split in splits
    ]


def test_source_leakage_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.csv"
        rows = complete_rows()
        rows.append({
            "filepath": "/audio/duplicate.wav",
            "label": "normal",
            "source_dataset": "field_test",
            # Reuses a source_clip_id complete_rows() already put in "train",
            # now also claimed for "validation" — the same source clip must
            # not appear in two splits.
            "source_clip_id": "source-normal-train",
            "split": "validation",
        })
        write_manifest(path, rows)
        result = validate_manifest(path)
        assert result["valid"] is False
        assert any("multiple splits" in blocker for blocker in result["blockers"])


def test_missing_validation_split_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.csv"
        rows = complete_rows()
        for row in rows:
            if row["split"] == "validation":
                row["split"] = "train"
        write_manifest(path, rows)
        result = validate_manifest(path)
        assert result["valid"] is False
        assert "Manifest has no validation split." in result["blockers"]


def test_complete_source_disjoint_manifest_is_valid():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.csv"
        write_manifest(path, complete_rows())
        result = validate_manifest(path)
        assert result["valid"] is True
        assert result["split_counts"]["test"] >= 1


def test_class_missing_from_one_split_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.csv"
        rows = complete_rows()
        # Drop "normal"'s only test-split row so it has train/validation but
        # no test coverage, even though the manifest overall still has a
        # non-empty test split (from every other class).
        rows = [r for r in rows if not (r["label"] == "normal" and r["split"] == "test")]
        write_manifest(path, rows)
        result = validate_manifest(path)
        assert result["valid"] is False
        assert "Class 'normal' has no test examples." in result["blockers"]


def test_unknown_source_dataset_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.csv"
        rows = complete_rows()
        rows[0]["source_dataset"] = "unknown"
        write_manifest(path, rows)
        result = validate_manifest(path)
        assert result["valid"] is False
        assert any("unknown" in blocker for blocker in result["blockers"])


if __name__ == "__main__":
    test_source_leakage_is_rejected()
    test_missing_validation_split_is_rejected()
    test_complete_source_disjoint_manifest_is_valid()
    test_class_missing_from_one_split_is_rejected()
    test_unknown_source_dataset_is_rejected()
    print("Data-manifest tests passed.")
