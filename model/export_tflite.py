"""Exports a combined YAMNet + trained-head model to TFLite for on-device use.

Unlike the removed PyTorch/CNN-Transformer export path (which depended on
ai-edge-torch, unavailable for this Python version, and an onnx-tf fallback
that is unmaintained and broken against current onnx releases), this is the
native, first-party TensorFlow export path: YAMNet is already a TF-Hub
SavedModel and the trained head is already Keras, so TFLiteConverter can
convert the combined graph directly with no intermediate format.
"""

import os

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

from audio_classes import YAMNET_HANDLE
from model_profiles import REAL_PROFILE_NAME, get_profile
from train_yamnet import _paths_for
from yamnet_features import load_yamnet, embed_waveform


class MeanMaxPoolAndClassify(tf.keras.layers.Layer):
    """Wraps YAMNet + the trained head into one graph, mirroring
    yamnet_features.embed_waveform's mean+max pooling exactly -- if this
    diverges from that function, the exported model silently stops matching
    what was trained and evaluated."""

    def __init__(self, head_model, **kwargs):
        super().__init__(**kwargs)
        self.yamnet_layer = hub.KerasLayer(YAMNET_HANDLE, trainable=False)
        self.head_model = head_model

    def call(self, waveform):
        _, embeddings, _ = self.yamnet_layer(waveform)
        mean_pooled = tf.reduce_mean(embeddings, axis=0)
        max_pooled = tf.reduce_max(embeddings, axis=0)
        pooled = tf.concat([mean_pooled, max_pooled], axis=0)
        return self.head_model(pooled[tf.newaxis, :])[0]


def build_combined_model(head_model):
    combined_layer = MeanMaxPoolAndClassify(head_model)
    waveform_input = tf.keras.Input(shape=(), dtype=tf.float32, name="waveform")
    class_probs = combined_layer(waveform_input)
    return tf.keras.Model(waveform_input, class_probs, name="echo_yamnet_combined")


def export_tflite(profile=REAL_PROFILE_NAME):
    profile = get_profile(profile) if isinstance(profile, str) else profile
    checkpoint_path = _paths_for(profile)["checkpoint"]
    print("Exporting combined YAMNet + hazard-head model to TFLite (profile: {})...".format(profile.name))

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(
            "Trained head not found at: {}. Please run train_yamnet.py --profile {} first.".format(
                checkpoint_path, profile.name
            )
        )

    head_model = tf.keras.models.load_model(checkpoint_path)
    combined_model = build_combined_model(head_model)

    # Sanity check the combined graph produces the SAME probabilities as
    # calling yamnet_features.embed_waveform() + the head directly (the exact
    # path used for training/evaluation/inference) on identical audio -- a
    # shape-only check would not catch a pooling/axis/ordering regression
    # that still produces a same-shape but numerically wrong result.
    rng = np.random.default_rng(seed=0)
    dummy_waveform = rng.standard_normal(32000).astype(np.float32)

    reference_yamnet = load_yamnet()
    reference_embedding, _ = embed_waveform(reference_yamnet, dummy_waveform)
    reference_probs = head_model.predict(reference_embedding[np.newaxis, :], verbose=0)[0]

    combined_probs = combined_model(dummy_waveform).numpy()

    assert combined_probs.shape == reference_probs.shape, (
        f"Combined model output shape {combined_probs.shape} does not match "
        f"reference shape {reference_probs.shape}."
    )
    assert np.allclose(combined_probs, reference_probs, atol=1e-4), (
        "Combined exported graph's output diverges from the reference "
        "embed_waveform()+head prediction -- the exported model no longer "
        "matches what was trained and evaluated.\n"
        f"combined={combined_probs}\nreference={reference_probs}"
    )
    print("Sanity check passed: exported graph matches the reference inference path.")

    converter = tf.lite.TFLiteConverter.from_keras_model(combined_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    # YAMNet contains ops (e.g. its internal STFT) outside the core TFLite
    # builtin set; select_tf_ops covers those without needing a custom
    # runtime build on the mobile side.
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS,
    ]
    tflite_model = converter.convert()

    os.makedirs("checkpoints", exist_ok=True)
    suffix = "" if profile.name == REAL_PROFILE_NAME else "_" + profile.name
    tflite_path = "checkpoints/echo_yamnet_model{}.tflite".format(suffix)
    with open(tflite_path, "wb") as f:
        f.write(tflite_model)

    head_size = os.path.getsize(checkpoint_path) / (1024 * 1024)
    tflite_size = os.path.getsize(tflite_path) / (1024 * 1024)
    print(f"TFLite model successfully exported to: {tflite_path}")
    print(f"Trained head checkpoint size: {head_size:.4f} MB")
    print(f"Combined quantized TFLite size: {tflite_size:.4f} MB")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=REAL_PROFILE_NAME)
    args = parser.parse_args()
    export_tflite(profile=args.profile)
