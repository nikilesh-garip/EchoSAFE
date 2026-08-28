"""Trains a small classifier head on top of frozen YAMNet embeddings.

Replaces model/train.py's from-scratch CNN-Transformer training. YAMNet was
pretrained on ~2M AudioSet clips; with only tens-to-hundreds of real clips
per hazard class, fine-tuning a small head on its embeddings has a far
better sample-efficiency ratio than training a transformer from zero, and it
gets a native TFLite export path for free (see export_tflite.py).

Two heads are trainable from this one script, selected with ``--profile``:

    python train_yamnet.py                  # production head (8 classes)
    python train_yamnet.py --profile demo   # demo head (+ firecracker class)

Both sit on the same frozen backbone, so the demo head costs one extra
softmax layer's worth of training, not a second model pipeline. See
model_profiles.py for why the firecracker class is kept out of the
production head.
"""

import hashlib
import json
import os

import numpy as np
import tensorflow as tf

from data_manifest import validate_manifest
from model_profiles import REAL_PROFILE_NAME, get_profile
from yamnet_features import EMBEDDING_DIM, load_yamnet, load_waveform, embed_waveform

EMBEDDING_FORMAT_VERSION = "meanmax-v1"  # bump when embed_waveform's output changes


def _paths_for(profile):
    """Per-profile artifact paths. The embedding cache is keyed by profile too:
    the demo manifest contains clips the production manifest does not, and
    sharing one cache file between them would silently reuse the wrong set."""
    suffix = "" if profile.name == REAL_PROFILE_NAME else "_" + profile.name
    return {
        "manifest": profile.manifest_path,
        "embedding_cache": os.path.join(
            "checkpoints", "yamnet_embeddings_cache{}.npz".format(suffix)
        ),
        "checkpoint": profile.checkpoint_path,
        "results": os.path.join(
            "checkpoints", "yamnet_training_results{}.json".format(suffix)
        ),
    }


def manifest_fingerprint(manifest_path, profile_name=REAL_PROFILE_NAME):
    with open(manifest_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return "{}:{}:{}".format(EMBEDDING_FORMAT_VERSION, profile_name, digest)


def _read_manifest_rows(manifest_path):
    import csv
    with open(manifest_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_or_load_embeddings(manifest_path, profile, cache_path):
    fingerprint = manifest_fingerprint(manifest_path, profile.name)

    if os.path.exists(cache_path):
        cache = np.load(cache_path, allow_pickle=True)
        if str(cache["fingerprint"]) == fingerprint:
            print("Reusing cached YAMNet embeddings (manifest unchanged).")
            return (
                cache["embeddings"], cache["labels"], cache["splits"], cache["filepaths"],
            )
        print("Manifest changed since last embedding cache; recomputing.")

    rows = _read_manifest_rows(manifest_path)
    print("Extracting YAMNet embeddings for {} clips (one-time, cached afterward)...".format(len(rows)))
    yamnet = load_yamnet()

    embeddings, labels, splits, filepaths = [], [], [], []
    for i, row in enumerate(rows):
        waveform = load_waveform(row["filepath"])
        embedding, _ = embed_waveform(yamnet, waveform)
        embeddings.append(embedding)
        labels.append(profile.class_mapping[row["label"]])
        splits.append(row["split"])
        filepaths.append(row["filepath"])
        if (i + 1) % 100 == 0:
            print("  {}/{} embedded...".format(i + 1, len(rows)))

    embeddings = np.stack(embeddings).astype(np.float32)
    labels = np.array(labels, dtype=np.int64)
    splits = np.array(splits)
    filepaths = np.array(filepaths)

    os.makedirs("checkpoints", exist_ok=True)
    np.savez(
        cache_path,
        embeddings=embeddings, labels=labels, splits=splits, filepaths=filepaths,
        fingerprint=fingerprint,
    )
    return embeddings, labels, splits, filepaths


def build_classifier_head(num_classes, hidden_units=128, dropout=0.3):
    # 2048-d input with only ~745 training examples is a lot of capacity for
    # a small, noisy dataset -- a smaller hidden layer plus L2 weight decay
    # trades some peak accuracy for a much less erratic validation curve.
    inputs = tf.keras.Input(shape=(EMBEDDING_DIM,), name="yamnet_embedding")
    x = tf.keras.layers.BatchNormalization()(inputs)
    x = tf.keras.layers.Dense(
        hidden_units, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-3),
    )(x)
    x = tf.keras.layers.Dropout(dropout)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax", name="hazard_class")(x)
    return tf.keras.Model(inputs, outputs, name="echo_yamnet_head")


def train_model(epochs=80, batch_size=16, hidden_units=256, dropout=0.3, lr=1e-3,
                profile=REAL_PROFILE_NAME):
    profile = get_profile(profile) if isinstance(profile, str) else profile
    paths = _paths_for(profile)
    print("Starting Echo YAMNet-head training (profile: {})...".format(profile.name))

    manifest_result = validate_manifest(
        paths["manifest"], target_classes=set(profile.class_mapping)
    )
    if not manifest_result["valid"]:
        raise RuntimeError(
            "{} failed manifest validation, refusing to train on it: ".format(paths["manifest"])
            + "; ".join(manifest_result["blockers"])
        )

    embeddings, labels, splits, filepaths = build_or_load_embeddings(
        paths["manifest"], profile, paths["embedding_cache"]
    )

    train_mask = splits == "train"
    val_mask = splits == "validation"
    test_mask = splits == "test"
    x_train, y_train = embeddings[train_mask], labels[train_mask]
    x_val, y_val = embeddings[val_mask], labels[val_mask]
    x_test, y_test = embeddings[test_mask], labels[test_mask]
    print("Dataset Split: Train={}, Val={}, Test={}".format(len(x_train), len(x_val), len(x_test)))

    # "normal" outnumbers every hazard class ~15-to-1 in this dataset; without
    # class weighting the head can minimize loss by mostly predicting normal,
    # which is exactly the wrong failure mode for a safety alarm.
    num_classes = profile.num_classes
    idx_to_class = profile.idx_to_class
    class_counts = np.bincount(y_train, minlength=num_classes)
    total = class_counts.sum()
    class_weight = {
        i: (total / (num_classes * count)) if count > 0 else 1.0
        for i, count in enumerate(class_counts)
    }
    print("Class weights (inverse frequency):",
          {idx_to_class[i]: round(w, 2) for i, w in class_weight.items()})

    model = build_classifier_head(num_classes, hidden_units=hidden_units, dropout=dropout)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    os.makedirs("checkpoints", exist_ok=True)
    # val_loss on a 158-example validation set is spiky (a handful of hard
    # examples can swing crossentropy a lot even when accuracy is stable);
    # val_accuracy is the more reliable signal at this sample size.
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=20, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(paths["checkpoint"], monitor="val_accuracy", save_best_only=True),
    ]

    history = model.fit(
        x_train, y_train,
        validation_data=(x_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=2,
    )

    model.save(paths["checkpoint"])

    results = {
        "profile": profile.name,
        "classes": sorted(profile.class_mapping, key=profile.class_mapping.get),
        "history": {k: [float(v) for v in vals] for k, vals in history.history.items()},
        "hidden_units": hidden_units,
        "dropout": dropout,
        "learning_rate": lr,
        "test_filepaths": filepaths[test_mask].tolist(),
        "test_labels": y_test.tolist(),
    }
    with open(paths["results"], "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("Training complete. Saved head to {} and results to {}.".format(
        paths["checkpoint"], paths["results"]))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hidden-units", type=int, default=256)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--profile", default=REAL_PROFILE_NAME,
                        help="Model profile to train: real (production) or demo (adds firecracker).")
    args = parser.parse_args()
    train_model(
        epochs=args.epochs, batch_size=args.batch_size,
        hidden_units=args.hidden_units, dropout=args.dropout, lr=args.lr,
        profile=args.profile,
    )
