import os
import numpy as np
import tensorflow as tf
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, accuracy_score

from model_profiles import REAL_PROFILE_NAME, get_profile
from model_readiness import assess_dataset_readiness
from evaluation_gates import assess_evaluation_gates
from train_yamnet import _paths_for, manifest_fingerprint


def evaluate_model(profile=REAL_PROFILE_NAME):
    profile = get_profile(profile) if isinstance(profile, str) else profile
    idx_to_class = profile.idx_to_class
    num_classes = profile.num_classes
    paths = _paths_for(profile)
    print("Starting Echo YAMNet-head Evaluation (profile: {})...".format(profile.name))

    if not os.path.exists(paths["embedding_cache"]) or not os.path.exists(paths["checkpoint"]):
        raise FileNotFoundError(
            "Trained head or embedding cache not found for profile '{}'. "
            "Please run train_yamnet.py --profile {} first.".format(profile.name, profile.name)
        )

    cache = np.load(paths["embedding_cache"], allow_pickle=True)
    # The cache is keyed by a fingerprint of metadata.csv at train time. If
    # the manifest changed since (relabeled clips, different split, more
    # data) without rerunning train_yamnet.py, this cache is stale --
    # evaluating against it would silently score a manifest that no longer
    # exists instead of failing loudly.
    current_fingerprint = manifest_fingerprint(paths["manifest"], profile.name)
    if str(cache["fingerprint"]) != current_fingerprint:
        raise RuntimeError(
            "Embedding cache is stale: {} has changed since train_yamnet.py last ran "
            "for profile '{}'. Re-run train_yamnet.py before evaluating.".format(
                paths["manifest"], profile.name
            )
        )
    splits = cache["splits"]
    test_mask = splits == "test"
    x_test = cache["embeddings"][test_mask]
    all_labels = cache["labels"][test_mask]

    model = tf.keras.models.load_model(paths["checkpoint"])
    probs = model.predict(x_test, verbose=0)
    all_preds = np.argmax(probs, axis=1)

    acc = accuracy_score(all_labels, all_preds)
    precision, recall, f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, average="macro", zero_division=0
    )
    class_precision, class_recall, class_f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, labels=list(range(num_classes)), zero_division=0
    )

    cm = confusion_matrix(all_labels, all_preds, labels=list(range(num_classes)))

    fprs, fnrs = [], []
    for i in range(num_classes):
        tp = cm[i, i]
        fn = np.sum(cm[i, :]) - tp
        fp = np.sum(cm[:, i]) - tp
        tn = np.sum(cm) - tp - fn - fp
        fprs.append(fp / (fp + tn) if (fp + tn) > 0 else 0.0)
        fnrs.append(fn / (fn + tp) if (fn + tp) > 0 else 0.0)

    class_keys = [idx_to_class[i] for i in range(num_classes)]
    class_names = [name.replace("_", " ").title() for name in class_keys]

    dataset_readiness = assess_dataset_readiness("data")
    release_gates = assess_evaluation_gates(
        dataset_ready=dataset_readiness["deployment_ready"],
        metrics={"macro_f1": f1},
        class_precision=dict(zip(class_keys, class_precision)),
        class_recall=dict(zip(class_keys, class_recall)),
        normal_false_positive_rate=fprs[0],
        # Playback is a separate hard-negative evaluation that has not yet been run.
        playback_false_positive_rate=None,
    )

    print("\n================ EVALUATION METRICS ================")
    print(f"Overall Accuracy:  {acc:.4f}")
    print(f"Macro Precision:   {precision:.4f}")
    print(f"Macro Recall:      {recall:.4f}")
    print(f"Macro F1 Score:    {f1:.4f}")
    print("====================================================")

    print("\nClass-wise Metrics:")
    print(f"{'Class':<20} | {'Precision':<9} | {'Recall':<8} | {'FPR':<8} | {'FNR':<8}")
    print("-" * 70)
    for i, name in enumerate(class_names):
        print(f"{name:<20} | {class_precision[i]:.4f}    | {class_recall[i]:.4f}   | {fprs[i]:.4f}   | {fnrs[i]:.4f}")

    print(f"\nRelease-ready for real-world claims: {release_gates['release_ready']}")
    for blocker in release_gates["blockers"]:
        print(f"  BLOCKER: {blocker}")

    print("\nConfusion Matrix:")
    print("   " + "   ".join(f"C{i}" for i in range(num_classes)))
    for i, row in enumerate(cm):
        print(f"C{i} " + " ".join(f"{val:4d}" for val in row) + f"  ({class_names[i]})")

    os.makedirs("../reports", exist_ok=True)
    suffix = "" if profile.name == REAL_PROFILE_NAME else "_" + profile.name
    report_path = "../reports/evaluation_report{}.txt".format(suffix)
    with open(report_path, "w") as f:
        f.write("Echo YAMNet Transfer-Learning Head Evaluation Report ({})\n".format(profile.name))
        f.write("=================================\n\n")
        f.write(f"Accuracy: {acc:.4f}\n")
        f.write(f"Precision: {precision:.4f}\n")
        f.write(f"Recall: {recall:.4f}\n")
        f.write(f"F1 Score: {f1:.4f}\n\n")
        f.write("Class-wise Metrics:\n")
        for i, name in enumerate(class_names):
            f.write(
                f"{name}: Precision={class_precision[i]:.4f}, Recall={class_recall[i]:.4f}, "
                f"FPR={fprs[i]:.4f}, FNR={fnrs[i]:.4f}\n"
            )
        f.write("\nConfusion Matrix:\n")
        f.write(np.array2string(cm) + "\n")
        f.write("\nReal-world release gates:\n")
        f.write(f"Ready: {release_gates['release_ready']}\n")
        for blocker in release_gates["blockers"]:
            f.write(f"BLOCKER: {blocker}\n")

    print(f"\nEvaluation Report successfully saved to: reports/evaluation_report{suffix}.txt")
    return {
        "accuracy": float(acc), "macro_precision": float(precision),
        "macro_recall": float(recall), "macro_f1": float(f1),
        "release_ready": release_gates["release_ready"],
        "blockers": release_gates["blockers"],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=REAL_PROFILE_NAME,
                        help="Model profile to evaluate: real (production) or demo.")
    args = parser.parse_args()
    evaluate_model(profile=args.profile)
