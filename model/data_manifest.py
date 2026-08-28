"""Dataset-manifest validation for reproducible, source-disjoint evaluations."""

import csv
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_COLUMNS = {
    "filepath", "label", "source_dataset", "source_clip_id", "split",
}
VALID_SPLITS = {"train", "validation", "test"}
TARGET_CLASSES = {
    "normal", "gunshot", "explosion", "scream", "glass_breaking",
    "fire_alarm", "siren", "shouting",
}


def validate_manifest(path: str | Path, target_classes: set | None = None) -> dict:
    """Validate provenance and ensure one source clip appears in only one split.

    ``target_classes`` lets the demo profile validate its own taxonomy (the
    eight production classes plus ``firecracker``) with the same contract,
    instead of forcing a second, driftable copy of this validator.
    """
    path = Path(path)
    target_classes = set(target_classes) if target_classes else set(TARGET_CLASSES)
    blockers = []
    class_counts = Counter()
    split_counts = Counter()
    class_split_counts = Counter()
    source_splits = defaultdict(set)

    if not path.exists():
        return {
            "valid": False,
            "record_count": 0,
            "class_counts": {},
            "split_counts": {},
            "blockers": [f"Manifest does not exist: {path}"],
        }

    with path.open(newline="", encoding="utf-8") as manifest:
        reader = csv.DictReader(manifest)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            return {
                "valid": False,
                "record_count": 0,
                "class_counts": {},
                "split_counts": {},
                "blockers": [f"Manifest is missing columns: {', '.join(sorted(missing))}."],
            }

        records = list(reader)

    if not records:
        blockers.append("Manifest has no recordings.")

    for row_number, row in enumerate(records, start=2):
        label = row["label"].strip()
        split = row["split"].strip().lower()
        source_id = row["source_clip_id"].strip()
        source_dataset = row["source_dataset"].strip()
        filepath = row["filepath"].strip()

        if label not in target_classes:
            blockers.append(f"Row {row_number} has unsupported label '{label}'.")
        if split not in VALID_SPLITS:
            blockers.append(f"Row {row_number} has invalid split '{split}'.")
        if not source_id or not source_dataset or not filepath:
            blockers.append(f"Row {row_number} is missing source or file provenance.")
        elif source_dataset == "unknown":
            blockers.append(
                f"Row {row_number} has an unrecognized source_dataset ('unknown'); "
                "every recording must be traceable to a real source."
            )

        class_counts[label] += 1
        split_counts[split] += 1
        if split in VALID_SPLITS:
            class_split_counts[(label, split)] += 1
        if source_id:
            source_splits[(source_dataset, source_id)].add(split)

    for (source_dataset, source_id), splits in sorted(source_splits.items()):
        if len(splits) > 1:
            blockers.append(
                f"Source clip '{source_dataset}:{source_id}' appears in multiple splits: "
                f"{', '.join(sorted(splits))}."
            )

    missing_classes = target_classes - set(class_counts)
    if missing_classes:
        blockers.append(f"Manifest is missing target classes: {', '.join(sorted(missing_classes))}.")
    for split in sorted(VALID_SPLITS):
        if split_counts[split] == 0:
            blockers.append(f"Manifest has no {split} split.")

    # A class present overall but absent from one split (a small class landing
    # entirely in "train" by chance, say) would otherwise pass silently: the
    # global "has a test split" check above only looks at split totals, not
    # per-class coverage within each split.
    for label in sorted(target_classes - missing_classes):
        for split in sorted(VALID_SPLITS):
            if class_split_counts[(label, split)] == 0:
                blockers.append(f"Class '{label}' has no {split} examples.")

    return {
        "valid": not blockers,
        "record_count": len(records),
        "class_counts": dict(sorted(class_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "blockers": blockers,
    }
