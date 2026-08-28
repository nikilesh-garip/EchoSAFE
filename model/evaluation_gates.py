"""Evidence-based release gates for Echo model evaluations.

The model can only be described as real-world ready when its evaluation data and
metrics are both independently sufficient.  This module deliberately keeps the
decision separate from a high score on synthetic audio.
"""

from dataclasses import dataclass
from typing import Mapping


REQUIRED_CLASSES = {
    "normal", "gunshot", "explosion", "scream", "glass_breaking",
    "fire_alarm", "siren", "shouting",
}


@dataclass(frozen=True)
class EvaluationGates:
    macro_f1: float = 0.95
    critical_recall: float = 0.98
    per_class_precision: float = 0.95
    normal_false_positive_rate: float = 0.01
    playback_false_positive_rate: float = 0.03


def assess_evaluation_gates(
    *,
    dataset_ready: bool,
    metrics: Mapping[str, float],
    class_precision: Mapping[str, float],
    class_recall: Mapping[str, float],
    normal_false_positive_rate: float | None,
    playback_false_positive_rate: float | None,
    gates: EvaluationGates = EvaluationGates(),
) -> dict:
    """Return a transparent release decision and every failed acceptance gate."""
    blockers = []

    if not dataset_ready:
        blockers.append("Evaluation data is not ready for a real-world model claim.")
    if metrics.get("macro_f1", 0.0) < gates.macro_f1:
        blockers.append(f"Macro F1 must be at least {gates.macro_f1:.2f}.")

    for class_name in sorted(REQUIRED_CLASSES):
        precision = class_precision.get(class_name)
        if precision is None or precision < gates.per_class_precision:
            blockers.append(
                f"{class_name} precision must be at least {gates.per_class_precision:.2f}."
            )

    for class_name in ("gunshot", "explosion", "fire_alarm"):
        recall = class_recall.get(class_name)
        if recall is None or recall < gates.critical_recall:
            blockers.append(
                f"{class_name} recall must be at least {gates.critical_recall:.2f}."
            )

    if normal_false_positive_rate is None or normal_false_positive_rate > gates.normal_false_positive_rate:
        blockers.append(
            f"Normal-audio false-positive rate must be at most {gates.normal_false_positive_rate:.2%}."
        )
    if playback_false_positive_rate is None or playback_false_positive_rate > gates.playback_false_positive_rate:
        blockers.append(
            f"Playback false-positive rate must be at most {gates.playback_false_positive_rate:.2%}."
        )

    return {
        "release_ready": not blockers,
        "blockers": blockers,
        "gates": {
            "macro_f1": gates.macro_f1,
            "critical_recall": gates.critical_recall,
            "per_class_precision": gates.per_class_precision,
            "normal_false_positive_rate": gates.normal_false_positive_rate,
            "playback_false_positive_rate": gates.playback_false_positive_rate,
        },
    }
