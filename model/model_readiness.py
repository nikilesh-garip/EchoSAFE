"""Truthful model-readiness checks used to block unsupported deployment claims."""

from collections import Counter
from pathlib import Path


HAZARD_CLASSES = {
    "normal", "gunshot", "explosion", "scream", "glass_breaking",
    "fire_alarm", "siren", "shouting",
}


def _is_synthetic(path):
    # Catches both the top-level data/synthetic/ tree and synthetic clips
    # copied into data/processed/<class>/ as a per-class fallback (prefixed
    # "synthetic_" by prepare_dataset.py's fill_missing_real_classes()).
    # Matching only path.parts would miss the second case, since those files
    # live under "processed" for training convenience but are not real
    # evidence — silently counting them as external broke the whole point of
    # this gate.
    return "synthetic" in path.parts or path.name.startswith("synthetic_")


def assess_dataset_readiness(data_root):
    root = Path(data_root)
    wav_files = list(root.rglob("*.wav")) if root.exists() else []
    class_counts = Counter(path.parent.name for path in wav_files)
    synthetic_count = sum(1 for path in wav_files if _is_synthetic(path))
    # Only curated, non-synthetic processed files count as externally sourced
    # evidence. Fixtures and arbitrary WAV files must not accidentally make a
    # model look validated.
    external_files = [
        path for path in wav_files if "processed" in path.parts and not _is_synthetic(path)
    ]
    external_count = len(external_files)
    external_class_counts = Counter(path.parent.name for path in external_files)
    missing_classes = sorted(HAZARD_CLASSES - set(class_counts))
    # A class with only synthetic clips must not read as "covered" just
    # because some other class in the same tree has real recordings.
    classes_without_real_evidence = sorted(HAZARD_CLASSES - set(external_class_counts))

    blockers = []
    if not wav_files:
        blockers.append("No WAV files are available for evaluation.")
    if external_count == 0 and synthetic_count > 0:
        blockers.append("Only synthetic audio is available; real-world accuracy cannot be claimed.")
    if missing_classes:
        blockers.append(f"Missing target classes: {', '.join(missing_classes)}.")
    if external_count > 0 and classes_without_real_evidence:
        blockers.append(
            "No externally sourced recordings for: "
            f"{', '.join(classes_without_real_evidence)}. These classes are synthetic-only."
        )
    if external_count < 1000:
        blockers.append("Fewer than 1,000 externally sourced recordings are available for holdout evaluation.")

    return {
        "deployment_ready": not blockers,
        "total_wav_files": len(wav_files),
        "synthetic_wav_files": synthetic_count,
        "external_wav_files": external_count,
        "class_counts": dict(sorted(class_counts.items())),
        "external_class_counts": dict(sorted(external_class_counts.items())),
        "blockers": blockers,
    }
