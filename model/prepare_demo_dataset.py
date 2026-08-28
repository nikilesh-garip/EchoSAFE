"""Builds the demo-profile dataset: production classes + firecracker.

    python prepare_demo_dataset.py

What it does
------------
1. Reuses the production manifest rows verbatim (same audio files, same
   source-disjoint splits). No audio is copied or duplicated -- the demo
   manifest simply points at ``data/processed/`` for the eight production
   classes, so the two heads see identical data for everything except the
   new class.
2. Ingests firecracker audio into ``data/processed_demo/firecracker/`` from,
   in priority order:
      a. ``data/raw/firecrackers/`` -- real recordings you drop in yourself
         (any layout, any common audio format). This is what you want for the
         demo: record 20-40 clips of the actual crackers you will light on
         stage, on the phone you will present with.
      b. ESC-50's ``fireworks`` category, if the ESC-50 zip was extracted by
         prepare_dataset.py. Real audio, but recorded far away and often
         reverberant, so it is a weaker match for a cracker lit three metres
         from the mic.
      c. ``data/synthetic/firecracker/`` -- the synthetic fallback from
         generate_synthetic_data.py, so the pipeline is always runnable.
3. Assigns a deterministic, source-disjoint 70/15/15 split by clip id and
   writes ``data/processed_demo/metadata.csv``, validated against the demo
   taxonomy with the same contract the production manifest must pass.

Why the production head must not get this data: see model_profiles.py.
"""

import csv
import glob
import hashlib
import os
import shutil

import librosa
import numpy as np
import soundfile as sf

from data_manifest import validate_manifest
from model_profiles import DEMO_PROFILE, REAL_PROFILE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FIRECRACKER_DIR = os.path.join(BASE_DIR, "data", "raw", "firecrackers")
SYNTHETIC_FIRECRACKER_DIR = os.path.join(BASE_DIR, "data", "synthetic", "firecracker")
ESC50_EXTRACT_DIR = os.path.join(BASE_DIR, "esc50_temp_dir")
DEMO_DIR = DEMO_PROFILE.dataset_dir
DEMO_FIRECRACKER_DIR = os.path.join(DEMO_DIR, "firecracker")

AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma")
MIN_CLIP_SECONDS = 4.5   # pass 2 verifies a 5s window; shorter clips get zero-padded
TARGET_SR = 16000


def _assign_split(clip_id):
    """Deterministic 70/15/15 by clip id -- same scheme as prepare_dataset.py,
    so a clip never lands in two different splits across runs."""
    bucket = int(hashlib.sha256(clip_id.encode("utf-8")).hexdigest(), 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _load_mono_16k(path):
    try:
        audio, sr = librosa.load(path, sr=TARGET_SR, mono=True)
        return audio
    except Exception as error:
        print("  skipped {} ({})".format(os.path.basename(path), error))
        return None


def _write_clip(audio, target_path):
    """Writes a >=4.5s clip. Long recordings are split into consecutive 5s
    windows so one 40-second Diwali recording becomes eight usable examples;
    short ones are tiled up to length rather than zero-padded, because a
    trailing block of digital silence teaches the head that silence is part
    of the class."""
    written = []
    window = int(5.0 * TARGET_SR)
    if len(audio) < int(MIN_CLIP_SECONDS * TARGET_SR):
        repeats = int(np.ceil(window / max(1, len(audio))))
        audio = np.tile(audio, repeats)[:window]

    total_windows = max(1, len(audio) // window)
    stem, ext = os.path.splitext(target_path)
    for index in range(total_windows):
        chunk = audio[index * window:(index + 1) * window]
        if len(chunk) < int(MIN_CLIP_SECONDS * TARGET_SR):
            break
        peak = float(np.max(np.abs(chunk))) if len(chunk) else 0.0
        if peak < 1e-4:
            continue  # a silent window is not a firecracker example
        chunk = chunk / peak * 0.9
        out_path = target_path if total_windows == 1 else "{}_w{:02d}{}".format(stem, index, ext)
        sf.write(out_path, chunk, TARGET_SR)
        written.append(out_path)
    return written


def _collect_source_files():
    """Returns (files, source_dataset_label) using the best source available."""
    real_files = []
    if os.path.isdir(RAW_FIRECRACKER_DIR):
        for root, _dirs, files in os.walk(RAW_FIRECRACKER_DIR):
            for name in files:
                if name.lower().endswith(AUDIO_EXTENSIONS):
                    real_files.append(os.path.join(root, name))
    if real_files:
        return sorted(real_files), "diwali_firecrackers_recorded"

    esc50_audio = os.path.join(ESC50_EXTRACT_DIR, "ESC-50-master", "audio")
    esc50_meta = os.path.join(ESC50_EXTRACT_DIR, "ESC-50-master", "meta", "esc50.csv")
    if os.path.exists(esc50_meta) and os.path.isdir(esc50_audio):
        fireworks = []
        with open(esc50_meta, newline="", encoding="utf-8") as meta:
            for row in csv.DictReader(meta):
                if row.get("category") == "fireworks":
                    candidate = os.path.join(esc50_audio, row["filename"])
                    if os.path.exists(candidate):
                        fireworks.append(candidate)
        if fireworks:
            return sorted(fireworks), "esc50_fireworks"

    synthetic = sorted(glob.glob(os.path.join(SYNTHETIC_FIRECRACKER_DIR, "*.wav")))
    return synthetic, "synthetic_firecracker"


def build_firecracker_class():
    if os.path.isdir(DEMO_FIRECRACKER_DIR):
        shutil.rmtree(DEMO_FIRECRACKER_DIR, ignore_errors=True)
    os.makedirs(DEMO_FIRECRACKER_DIR, exist_ok=True)

    files, source_dataset = _collect_source_files()
    if not files:
        raise RuntimeError(
            "No firecracker audio found. Drop recordings into {} or run "
            "`python generate_synthetic_data.py --firecracker-only` first.".format(
                RAW_FIRECRACKER_DIR
            )
        )

    print("Firecracker source: {} ({} files)".format(source_dataset, len(files)))
    if source_dataset == "synthetic_firecracker":
        print("  NOTE: synthetic fallback in use. The demo head will work, but for a "
              "convincing on-stage demo record real crackers into "
              + RAW_FIRECRACKER_DIR)

    records = []
    for source_path in files:
        audio = _load_mono_16k(source_path)
        if audio is None:
            continue
        clip_id = os.path.splitext(os.path.basename(source_path))[0]
        target = os.path.join(DEMO_FIRECRACKER_DIR, "firecracker_{}.wav".format(clip_id))
        for written_path in _write_clip(audio, target):
            records.append({
                "filepath": os.path.abspath(written_path),
                "label": "firecracker",
                "source_dataset": source_dataset,
                # Split by the *source recording*, not the derived window:
                # two 5-second windows cut from the same recording are near
                # duplicates, and letting them straddle train/test would
                # inflate the demo head's reported accuracy.
                "source_clip_id": clip_id,
                "split": _assign_split(clip_id),
            })
    print("Wrote {} firecracker windows from {} source recordings.".format(
        len(records), len(files)))
    return records


def load_production_records():
    manifest = REAL_PROFILE.manifest_path
    if not os.path.exists(manifest):
        raise RuntimeError(
            "Production manifest missing at {}. Run prepare_dataset.py first.".format(manifest)
        )
    with open(manifest, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    os.makedirs(DEMO_DIR, exist_ok=True)
    records = load_production_records()
    print("Reusing {} production records (no audio duplicated).".format(len(records)))
    records = records + build_firecracker_class()

    out_csv = DEMO_PROFILE.manifest_path
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filepath", "label", "source_dataset", "source_clip_id", "split"]
        )
        writer.writeheader()
        writer.writerows(records)

    result = validate_manifest(out_csv, target_classes=set(DEMO_PROFILE.class_mapping))
    if not result["valid"]:
        print("\nDEMO MANIFEST VALIDATION FAILED:")
        for blocker in result["blockers"]:
            print("  BLOCKER: {}".format(blocker))
        raise RuntimeError("Demo manifest failed validation; refusing to hand it to training.")

    print("\nDemo manifest written to {}".format(out_csv))
    print("Class counts: {}".format(result["class_counts"]))
    print("Split counts: {}".format(result["split_counts"]))
    print("\nNext: python train_yamnet.py --profile demo")


if __name__ == "__main__":
    build()
