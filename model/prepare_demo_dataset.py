"""Builds the demo-profile dataset: production classes + firecracker.

    python prepare_demo_dataset.py
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
ESC50_EXTRACT_DIR = os.path.join(BASE_DIR, "data")
DEMO_DIR = DEMO_PROFILE.dataset_dir
DEMO_FIRECRACKER_DIR = os.path.join(DEMO_DIR, "firecracker")

AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma")
MIN_CLIP_SECONDS = 4.5
TARGET_SR = 16000


def _assign_split(clip_id):
    bucket = int(hashlib.sha256(clip_id.encode("utf-8")).hexdigest(), 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _load_mono_16k(path):
    try:
        audio, sr = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if sr != TARGET_SR:
            import scipy.signal
            num_samples = int(len(audio) * TARGET_SR / sr)
            audio = scipy.signal.resample(audio, num_samples)
        return audio.astype(np.float32)
    except Exception as error:
        print("  skipped {} ({})".format(os.path.basename(path), error))
        return None


def _write_clip(audio, target_path):
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
            continue
        chunk = chunk / peak * 0.9
        out_path = target_path if total_windows == 1 else "{}_w{:02d}{}".format(stem, index, ext)
        sf.write(out_path, chunk, TARGET_SR)
        written.append(out_path)
    return written


def _collect_source_files():
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

    processed_fc = sorted(glob.glob(os.path.join(BASE_DIR, "data", "processed", "firecracker", "*.wav")))
    if processed_fc:
        return processed_fc, "real_firecrackers_processed"

    synthetic = sorted(glob.glob(os.path.join(SYNTHETIC_FIRECRACKER_DIR, "*.wav")))
    return synthetic, "synthetic_firecracker"


def build_firecracker_class():
    if os.path.isdir(DEMO_FIRECRACKER_DIR):
        shutil.rmtree(DEMO_FIRECRACKER_DIR, ignore_errors=True)
    os.makedirs(DEMO_FIRECRACKER_DIR, exist_ok=True)

    files, source_dataset = _collect_source_files()
    if not files:
        raise RuntimeError("No firecracker audio found.")

    print("Firecracker source: {} ({} files)".format(source_dataset, len(files)))
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


def build_demo_manifest():
    print("Building demo-profile dataset ({}) ...".format(DEMO_PROFILE.name))
    production_records = load_production_records()
    firecracker_records = build_firecracker_class()

    all_records = production_records + firecracker_records
    manifest_path = DEMO_PROFILE.manifest_path
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    fieldnames = ["filepath", "label", "source_dataset", "source_clip_id", "split"]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_records:
            writer.writerow({k: row[k] for k in fieldnames})

    print("Wrote demo manifest: {} ({} total rows)".format(
        manifest_path, len(all_records)))

    result = validate_manifest(
        manifest_path,
        target_classes=set(DEMO_PROFILE.class_mapping),
        
    )
    if not result["valid"]:
        print("DEMO MANIFEST VALIDATION FAILED:")
        for blocker in result["blockers"]:
            print("  BLOCKER:", blocker)
        raise RuntimeError("Demo manifest failed validation.")

    print("Demo manifest validated cleanly against demo taxonomy ({} classes).".format(
        DEMO_PROFILE.num_classes))
    print("Demo split counts:", result["split_counts"])


if __name__ == "__main__":
    build_demo_manifest()
