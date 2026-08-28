"""Exports the combined YAMNet + hazard-head model to OpenVINO IR.

Ported from the removed PyTorch/CNN-Transformer export path to the current
TensorFlow/YAMNet model (see export_tflite.py for the combined-model
construction this reuses). Kept because laptop-side OpenVINO benchmarking on
Intel iGPU hardware is a documented differentiator (TIER_TABLE.md #12), not
because it is required for the mobile app itself.
"""

import os

import tensorflow as tf

from model_profiles import REAL_PROFILE_NAME, get_profile
from train_yamnet import _paths_for
from export_tflite import build_combined_model


def export_openvino(profile=REAL_PROFILE_NAME):
    profile = get_profile(profile) if isinstance(profile, str) else profile
    checkpoint_path = _paths_for(profile)["checkpoint"]
    print("Exporting combined YAMNet + hazard-head model to OpenVINO IR (profile: {})...".format(profile.name))

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(
            "Trained head not found at: {}. Please run train_yamnet.py --profile {} first.".format(
                checkpoint_path, profile.name
            )
        )

    try:
        import openvino as ov
    except ImportError:
        print("openvino package not found. Installing now...")
        os.system("pip install openvino")
        import openvino as ov

    head_model = tf.keras.models.load_model(checkpoint_path)
    combined_model = build_combined_model(head_model)

    suffix = "" if profile.name == REAL_PROFILE_NAME else "_" + profile.name

    # Passing the in-memory Keras object directly hits an OpenVINO/TF
    # version-introspection bug in this environment (openvino 2026.3 against
    # tensorflow 2.21); converting from an on-disk SavedModel is the more
    # robust path and is what OpenVINO's own docs recommend for TF models.
    saved_model_dir = "checkpoints/echo_yamnet_saved_model{}".format(suffix)
    combined_model.export(saved_model_dir)
    ov_model = ov.convert_model(saved_model_dir)

    output_dir = "checkpoints/openvino{}".format(suffix)
    os.makedirs(output_dir, exist_ok=True)
    ov.save_model(ov_model, os.path.join(output_dir, "echo_yamnet_model.xml"))

    print(f"OpenVINO IR model successfully saved under: {output_dir}/")
    print(f"  - XML file: {output_dir}/echo_yamnet_model.xml")
    print(f"  - BIN file: {output_dir}/echo_yamnet_model.bin")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=REAL_PROFILE_NAME)
    args = parser.parse_args()
    export_openvino(profile=args.profile)
