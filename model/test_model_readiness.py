import tempfile
from pathlib import Path

from model_readiness import HAZARD_CLASSES, assess_dataset_readiness


def _write_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Content is irrelevant: assess_dataset_readiness only looks at paths/names.
    path.write_bytes(b"RIFF....WAVEfmt ")


def test_empty_directory_blocks_deployment():
    with tempfile.TemporaryDirectory() as directory:
        result = assess_dataset_readiness(Path(directory))
        assert result["deployment_ready"] is False
        assert any("No WAV files" in blocker for blocker in result["blockers"])


def test_synthetic_only_blocks_deployment():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for cls in HAZARD_CLASSES:
            _write_wav(root / "synthetic" / cls / f"{cls}_000.wav")
        result = assess_dataset_readiness(root)
        assert result["deployment_ready"] is False
        assert result["external_wav_files"] == 0
        assert any("synthetic" in blocker.lower() for blocker in result["blockers"])


def test_real_data_missing_for_one_class_blocks_deployment():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for cls in HAZARD_CLASSES:
            _write_wav(root / "synthetic" / cls / f"{cls}_000.wav")
        # Every class except "scream" gets real (processed) coverage.
        covered_classes = HAZARD_CLASSES - {"scream"}
        for cls in covered_classes:
            for i in range(150):
                _write_wav(root / "processed" / cls / f"{cls}_real_{i:03d}.wav")
        result = assess_dataset_readiness(root)
        assert result["deployment_ready"] is False
        assert any("scream" in blocker for blocker in result["blockers"])


def test_synthetic_fallback_copied_into_processed_is_not_counted_as_real():
    # prepare_dataset.py's fill_missing_real_classes() copies synthetic clips
    # into data/processed/<class>/synthetic_*.wav (not data/synthetic/) so the
    # class stays trainable. Those files must still not count as real
    # evidence just because they live under "processed".
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        covered_classes = HAZARD_CLASSES - {"scream"}
        for cls in covered_classes:
            for i in range(150):
                _write_wav(root / "processed" / cls / f"{cls}_real_{i:03d}.wav")
        for i in range(50):
            _write_wav(root / "processed" / "scream" / f"synthetic_scream_{i:03d}.wav")
        result = assess_dataset_readiness(root)
        assert result["deployment_ready"] is False
        assert "scream" not in result["external_class_counts"]
        assert any("scream" in blocker for blocker in result["blockers"])


def test_full_real_coverage_above_threshold_is_deployment_ready():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for cls in HAZARD_CLASSES:
            for i in range(150):
                _write_wav(root / "processed" / cls / f"{cls}_real_{i:03d}.wav")
        result = assess_dataset_readiness(root)
        assert result["deployment_ready"] is True
        assert result["blockers"] == []


if __name__ == "__main__":
    test_empty_directory_blocks_deployment()
    test_synthetic_only_blocks_deployment()
    test_real_data_missing_for_one_class_blocks_deployment()
    test_synthetic_fallback_copied_into_processed_is_not_counted_as_real()
    test_full_real_coverage_above_threshold_is_deployment_ready()
    print("Model readiness tests passed.")
