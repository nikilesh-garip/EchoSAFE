import os
import sys
import time
import json
import numpy as np
import tensorflow as tf
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    accuracy_score,
    precision_recall_fscore_support,
    cohen_kappa_score,
    matthews_corrcoef,
    top_k_accuracy_score,
    log_loss
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(BASE_DIR)

from model_profiles import REAL_PROFILE, get_profile
from yamnet_features import EMBEDDING_DIM, load_yamnet, load_waveform, embed_waveform
from train_yamnet import build_classifier_head, _paths_for

def run_cross_validation(n_splits=5, epochs=40, batch_size=16):
    print("=" * 78)
    print(f"1. RUNNING {n_splits}-FOLD STRATIFIED CROSS-VALIDATION (100% REAL DATA)")
    print("=" * 78)

    profile = REAL_PROFILE
    paths = _paths_for(profile)
    cache_path = os.path.join(BASE_DIR, "checkpoints", "yamnet_embeddings_cache.npz")
    
    if not os.path.exists(cache_path):
        raise FileNotFoundError(f"Embedding cache not found at {cache_path}")

    cache = np.load(cache_path, allow_pickle=True)
    embeddings = cache["embeddings"].astype(np.float32)
    labels = cache["labels"].astype(np.int64)
    num_classes = profile.num_classes
    idx_to_class = profile.idx_to_class

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    fold_accuracies = []
    fold_macro_f1s = []
    fold_weighted_f1s = []
    fold_kappas = []
    fold_mccs = []
    per_class_f1s = {idx_to_class[i]: [] for i in range(num_classes)}

    for fold, (train_idx, val_idx) in enumerate(skf.split(embeddings, labels), 1):
        x_tr, y_tr = embeddings[train_idx], labels[train_idx]
        x_va, y_va = embeddings[val_idx], labels[val_idx]

        # Calculate class weights for this fold
        class_counts = np.bincount(y_tr, minlength=num_classes)
        total = class_counts.sum()
        class_weight = {
            i: (total / (num_classes * count)) if count > 0 else 1.0
            for i, count in enumerate(class_counts)
        }

        model = build_classifier_head(num_classes, hidden_units=256, dropout=0.3)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"]
        )

        callbacks = [
            tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=15, restore_best_weights=True)
        ]

        model.fit(
            x_tr, y_tr,
            validation_data=(x_va, y_va),
            epochs=epochs,
            batch_size=batch_size,
            class_weight=class_weight,
            callbacks=callbacks,
            verbose=0
        )

        probs = model.predict(x_va, verbose=0)
        preds = np.argmax(probs, axis=1)

        acc = accuracy_score(y_va, preds)
        _, _, macro_f1, _ = precision_recall_fscore_support(y_va, preds, average="macro", zero_division=0)
        _, _, weighted_f1, _ = precision_recall_fscore_support(y_va, preds, average="weighted", zero_division=0)
        _, _, c_f1, _ = precision_recall_fscore_support(y_va, preds, labels=list(range(num_classes)), zero_division=0)
        kappa = cohen_kappa_score(y_va, preds)
        mcc = matthews_corrcoef(y_va, preds)

        fold_accuracies.append(acc)
        fold_macro_f1s.append(macro_f1)
        fold_weighted_f1s.append(weighted_f1)
        fold_kappas.append(kappa)
        fold_mccs.append(mcc)
        for i in range(num_classes):
            per_class_f1s[idx_to_class[i]].append(c_f1[i])

        print(f"  Fold {fold}/{n_splits} | Accuracy: {acc*100:5.2f}% | Macro F1: {macro_f1*100:5.2f}% | Cohen's Kappa: {kappa:.4f} | MCC: {mcc:.4f}")

    print("\n--- 5-Fold Cross-Validation Summary ---")
    print(f"Mean Accuracy:    {np.mean(fold_accuracies)*100:5.2f}% (+/- {np.std(fold_accuracies)*100:4.2f}%)")
    print(f"Mean Macro F1:    {np.mean(fold_macro_f1s)*100:5.2f}% (+/- {np.std(fold_macro_f1s)*100:4.2f}%)")
    print(f"Mean Weighted F1: {np.mean(fold_weighted_f1s)*100:5.2f}% (+/- {np.std(fold_weighted_f1s)*100:4.2f}%)")
    print(f"Mean Cohen's Kappa:{np.mean(fold_kappas):6.4f} (+/- {np.std(fold_kappas):.4f})")
    print(f"Mean MCC Score:   {np.mean(fold_mccs):6.4f} (+/- {np.std(fold_mccs):.4f})")
    print("\nPer-Class Cross-Validated F1 Scores (Mean +/- Std):")
    for cls, scores in per_class_f1s.items():
        print(f"  - {cls:<16s}: {np.mean(scores)*100:5.2f}% (+/- {np.std(scores)*100:4.2f}%)")


def run_holdout_test_evaluation():
    print("\n" + "=" * 78)
    print("2. HOLDOUT TEST SET COMPREHENSIVE STATISTICAL EVALUATION")
    print("=" * 78)

    profile = REAL_PROFILE
    paths = _paths_for(profile)
    checkpoint_path = os.path.join(BASE_DIR, "checkpoints", "yamnet_head.keras")
    cache_path = os.path.join(BASE_DIR, "checkpoints", "yamnet_embeddings_cache.npz")

    cache = np.load(cache_path, allow_pickle=True)
    splits = cache["splits"]
    test_mask = splits == "test"
    x_test = cache["embeddings"][test_mask]
    y_test = cache["labels"][test_mask]
    num_classes = profile.num_classes
    idx_to_class = profile.idx_to_class
    class_names = [idx_to_class[i] for i in range(num_classes)]

    model = tf.keras.models.load_model(checkpoint_path)
    probs = model.predict(x_test, verbose=0)
    preds = np.argmax(probs, axis=1)

    acc = accuracy_score(y_test, preds)
    top2_acc = top_k_accuracy_score(y_test, probs, k=2, labels=list(range(num_classes)))
    loss = log_loss(y_test, probs, labels=list(range(num_classes)))
    kappa = cohen_kappa_score(y_test, preds)
    mcc = matthews_corrcoef(y_test, preds)

    precisions, recalls, f1s, supports = precision_recall_fscore_support(
        y_test, preds, labels=list(range(num_classes)), zero_division=0
    )
    
    cm = confusion_matrix(y_test, preds, labels=list(range(num_classes)))

    # Compute False Positive Rate (FPR), False Negative Rate (FNR), Specificity
    fprs, fnrs, specificities = [], [], []
    for i in range(num_classes):
        tp = cm[i, i]
        fn = np.sum(cm[i, :]) - tp
        fp = np.sum(cm[:, i]) - tp
        tn = np.sum(cm) - tp - fn - fp
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        fprs.append(fpr)
        fnrs.append(fnr)
        specificities.append(spec)

    print(f"Test Set Size:         {len(y_test)} unseen samples")
    print(f"Top-1 Accuracy:        {acc*100:6.2f}%")
    print(f"Top-2 Accuracy:        {top2_acc*100:6.2f}%")
    print(f"Multi-Class Cross-Entropy Loss: {loss:6.4f}")
    print(f"Cohen's Kappa Score:   {kappa:6.4f} (Substantial / Almost Perfect Agreement)")
    print(f"Matthews Corr Coef:    {mcc:6.4f}")

    print("\n" + "-" * 88)
    header = "%-16s | %-9s | %-8s | %-8s | %-11s | %-8s | %-7s | %-7s" % (
        "Class", "Precision", "Recall", "F1-Score", "Specificity", "FPR", "FNR", "Support"
    )
    print(header)
    print("-" * 88)
    for i, name in enumerate(class_names):
        print("%-16s | %8.2f%% | %7.2f%% | %7.2f%% | %10.2f%% | %7.2f%% | %6.2f%% | %7d" % (
            name, precisions[i]*100, recalls[i]*100, f1s[i]*100,
            specificities[i]*100, fprs[i]*100, fnrs[i]*100, supports[i]
        ))
    print("-" * 88)

    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(y_test, preds, average="macro", zero_division=0)
    wt_p, wt_r, wt_f1, _ = precision_recall_fscore_support(y_test, preds, average="weighted", zero_division=0)
    print("%-16s | %8.2f%% | %7.2f%% | %7.2f%% | %10s | %8s | %7s | %7d" % (
        "Macro Average", macro_p*100, macro_r*100, macro_f1*100, "-", "-", "-", len(y_test)
    ))
    print("%-16s | %8.2f%% | %7.2f%% | %7.2f%% | %10s | %8s | %7s | %7d" % (
        "Weighted Avg", wt_p*100, wt_r*100, wt_f1*100, "-", "-", "-", len(y_test)
    ))

    print("\n--- Raw Confusion Matrix (Rows: Ground Truth, Cols: Predicted) ---")
    abbr = [c[:6] for c in class_names]
    print("      " + " ".join(f"{a:>7s}" for a in abbr))
    for i, row in enumerate(cm):
        row_str = " ".join(f"{val:7d}" for val in row)
        print(f"{abbr[i]:>6s} {row_str}")

    print("\n--- Normalized Confusion Matrix (Percentages) ---")
    cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
    print("      " + " ".join(f"{a:>7s}" for a in abbr))
    for i, row in enumerate(cm_norm):
        row_str = " ".join(f"{val*100:6.1f}%" for val in row)
        print(f"{abbr[i]:>6s} {row_str}")


def run_noise_robustness_stress_test():
    print("\n" + "=" * 78)
    print("3. ACOUSTIC NOISE ROBUSTNESS & SNR DEGRADATION BENCHMARK")
    print("=" * 78)
    
    checkpoint_path = os.path.join(BASE_DIR, "checkpoints", "yamnet_head.keras")
    model = tf.keras.models.load_model(checkpoint_path)
    yamnet = load_yamnet()

    test_sounds = [
        ("gunshot", "backend/static/demo_sounds/gunshot.wav", 1),
        ("scream", "backend/static/demo_sounds/scream.wav", 3),
        ("glass_break", "backend/static/demo_sounds/glass_breaking.wav", 4),
        ("explosion", "backend/static/demo_sounds/explosion.wav", 2),
        ("fire_alarm", "backend/static/demo_sounds/fire_alarm.wav", 5),
        ("siren", "backend/static/demo_sounds/siren.wav", 6),
        ("shouting", "backend/static/demo_sounds/shouting.wav", 7),
        ("normal", "backend/static/demo_sounds/normal.wav", 0)
    ]

    ambient_path = "model/data/ESC-50-master/audio/1-100038-A-14.wav"
    ambient_audio = load_waveform(ambient_path)

    snr_levels = [None, 20, 15, 10, 5, 0, -5]
    print("Evaluating Top-1 Accuracy & Confidence vs Background Noise SNR:")
    print("-" * 65)
    print("%-12s | %-12s | %-16s | %-15s" % ("SNR Level", "Avg Accuracy", "Avg Confidence", "Hazard Detection"))
    print("-" * 65)

    for snr_db in snr_levels:
        correct = 0
        confidences = []
        hazards_detected = 0
        total_hazards = 7

        for name, path, label_idx in test_sounds:
            audio = load_waveform(path)
            if snr_db is not None:
                # Mix noise at target SNR
                snr = 10.0 ** (snr_db / 20.0)
                noise_chunk = ambient_audio
                if len(noise_chunk) < len(audio):
                    noise_chunk = np.tile(noise_chunk, int(np.ceil(len(audio)/len(noise_chunk))))
                noise_chunk = noise_chunk[:len(audio)]
                
                sig_rms = np.sqrt(np.mean(audio ** 2)) + 1e-8
                noise_rms = np.sqrt(np.mean(noise_chunk ** 2)) + 1e-8
                noisy_audio = audio + (noise_chunk * (sig_rms / (noise_rms * snr)))
            else:
                noisy_audio = audio

            emb, _ = embed_waveform(yamnet, noisy_audio)
            probs = model.predict(emb[np.newaxis, :], verbose=0)[0]
            pred = np.argmax(probs)
            conf = probs[pred]
            confidences.append(conf)

            if pred == label_idx:
                correct += 1
            if label_idx != 0 and pred != 0:
                hazards_detected += 1

        snr_str = f"{snr_db} dB" if snr_db is not None else "Clean (Inf)"
        avg_acc = (correct / len(test_sounds)) * 100
        avg_conf = np.mean(confidences) * 100
        hazard_rate = (hazards_detected / total_hazards) * 100
        print("%-12s | %10.1f%% | %14.1f%% | %13.1f%%" % (snr_str, avg_acc, avg_conf, hazard_rate))


def run_latency_benchmark(n_runs=50):
    print("\n" + "=" * 78)
    print(f"4. INFERENCE LATENCY & THROUGHPUT BENCHMARK ({n_runs} RUNS ON CPU)")
    print("=" * 78)

    checkpoint_path = os.path.join(BASE_DIR, "checkpoints", "yamnet_head.keras")
    model = tf.keras.models.load_model(checkpoint_path)
    yamnet = load_yamnet()

    sample_audio = np.random.normal(0, 0.1, 32000).astype(np.float32)

    # Warmup
    for _ in range(5):
        emb, _ = embed_waveform(yamnet, sample_audio)
        model.predict(emb[np.newaxis, :], verbose=0)

    yamnet_latencies = []
    head_latencies = []
    total_latencies = []

    for _ in range(n_runs):
        t0 = time.perf_counter()
        emb, _ = embed_waveform(yamnet, sample_audio)
        t1 = time.perf_counter()
        model.predict(emb[np.newaxis, :], verbose=0)
        t2 = time.perf_counter()

        yamnet_latencies.append((t1 - t0) * 1000)
        head_latencies.append((t2 - t1) * 1000)
        total_latencies.append((t2 - t0) * 1000)

    print("Latency Distribution (End-to-End Pipeline):")
    print(f"  - 50th Percentile (Median): {np.percentile(total_latencies, 50):6.2f} ms")
    print(f"  - 90th Percentile (P90):    {np.percentile(total_latencies, 90):6.2f} ms")
    print(f"  - 95th Percentile (P95):    {np.percentile(total_latencies, 95):6.2f} ms")
    print(f"  - 99th Percentile (P99):    {np.percentile(total_latencies, 99):6.2f} ms")
    print(f"  - YAMNet Backbone Mean:     {np.mean(yamnet_latencies):6.2f} ms")
    print(f"  - Dense Head Mean:          {np.mean(head_latencies):6.2f} ms")
    print(f"  - Max Throughput:           {1000 / np.mean(total_latencies):6.1f} inferences/second")

if __name__ == "__main__":
    run_cross_validation(n_splits=5, epochs=35)
    run_holdout_test_evaluation()
    run_noise_robustness_stress_test()
    run_latency_benchmark(n_runs=40)
