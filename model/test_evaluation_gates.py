from evaluation_gates import assess_evaluation_gates


CLASSES = {
    "normal", "gunshot", "explosion", "scream", "glass_breaking",
    "fire_alarm", "siren", "shouting",
}


def test_incomplete_evidence_is_rejected_despite_high_metrics():
    result = assess_evaluation_gates(
        dataset_ready=False,
        metrics={"macro_f1": 1.0},
        class_precision={name: 1.0 for name in CLASSES},
        class_recall={name: 1.0 for name in CLASSES},
        normal_false_positive_rate=0.0,
        playback_false_positive_rate=0.0,
    )
    assert result["release_ready"] is False
    assert any("data is not ready" in blocker for blocker in result["blockers"])


def test_complete_evidence_passes_all_gates():
    result = assess_evaluation_gates(
        dataset_ready=True,
        metrics={"macro_f1": 0.96},
        class_precision={name: 0.96 for name in CLASSES},
        class_recall={name: 0.99 for name in CLASSES},
        normal_false_positive_rate=0.01,
        playback_false_positive_rate=0.03,
    )
    assert result["release_ready"] is True


if __name__ == "__main__":
    test_incomplete_evidence_is_rejected_despite_high_metrics()
    test_complete_evidence_passes_all_gates()
    print("Evaluation gate tests passed.")
