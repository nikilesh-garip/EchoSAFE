import hashlib
import os
import re
import zipfile
import csv
import shutil
import numpy as np
import soundfile as sf
import librosa
import glob

from data_manifest import validate_manifest

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
RAW_US8K_DIR = os.path.join(BASE_DIR, "data", "raw", "UrbanSound8K")
ZIP_ESC50_PATH = os.path.join(BASE_DIR, "esc50_temp.zip")
SYNTHETIC_DIR = os.path.join(BASE_DIR, "data", "synthetic")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

ACTIVE_CLASSES = [
    "normal", "gunshot", "explosion", "scream", "glass_breaking",
    "fire_alarm", "siren", "shouting",
]


def setup_directories():
    print("Clearing and setting up processed directories...")
    if os.path.exists(PROCESSED_DIR):
        # Clear contents rather than rmtree-ing the directory node itself:
        # under OneDrive/cloud-sync folders the directory handle can still be
        # held by the sync client for a moment after its children are gone,
        # which turns rmtree(PROCESSED_DIR) into an intermittent
        # PermissionError on Windows.
        for entry in os.listdir(PROCESSED_DIR):
            entry_path = os.path.join(PROCESSED_DIR, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path, ignore_errors=True)
            else:
                os.remove(entry_path)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    for c in ACTIVE_CLASSES:
        os.makedirs(os.path.join(PROCESSED_DIR, c), exist_ok=True)

def process_audio_file(source_path, target_path):
    """Loads, converts to mono, resamples to 16kHz, and saves the audio."""
    try:
        audio, sr = sf.read(source_path)
        # Convert to mono if multi-channel
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        # Resample to 16000 Hz if needed
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        # Save
        sf.write(target_path, audio, 16000)
        return True
    except Exception as e:
        print(f"Error processing file {source_path}: {e}")
        return False

def ingest_urbansound8k():
    print("\nProcessing UrbanSound8K dataset...")
    csv_path = os.path.join(RAW_US8K_DIR, "UrbanSound8K.csv")
    if not os.path.exists(csv_path):
        print(f"UrbanSound8K metadata not found at: {csv_path}. Skipping UrbanSound8K.")
        return

    # Counts for category balancing
    counts = {
        "gunshot": 0,
        "siren": 0,
        "normal": {}  # dict of sub-category counts to balance background noises
    }
    
    max_normal_per_subclass = 50  # 8 background classes * 50 = 400 normal samples
    max_gunshot = 350
    max_siren = 300

    processed_count = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            us_class = row['class']
            slice_file_name = row['slice_file_name']
            fold = f"fold{row['fold']}"
            
            source_path = os.path.join(RAW_US8K_DIR, fold, slice_file_name)
            if not os.path.exists(source_path):
                continue

            target_class = None
            if us_class == "gun_shot":
                if counts["gunshot"] < max_gunshot:
                    target_class = "gunshot"
                    counts["gunshot"] += 1
            elif us_class == "siren":
                if counts["siren"] < max_siren:
                    target_class = "siren"
                    counts["siren"] += 1
            else:
                # Map other 8 categories to normal
                subclass_count = counts["normal"].get(us_class, 0)
                if subclass_count < max_normal_per_subclass:
                    target_class = "normal"
                    counts["normal"][us_class] = subclass_count + 1

            if target_class:
                target_path = os.path.join(PROCESSED_DIR, target_class, f"us8k_{slice_file_name}")
                if process_audio_file(source_path, target_path):
                    processed_count += 1

    print(f"UrbanSound8K Ingestion Complete: processed {processed_count} files.")
    print(f"  - Gunshot: {counts['gunshot']}")
    print(f"  - Siren: {counts['siren']}")
    print(f"  - Normal: {sum(counts['normal'].values())} (from background subclasses)")

def ingest_esc50():
    print("\nProcessing ESC-50 dataset...")
    if not os.path.exists(ZIP_ESC50_PATH):
        print(f"ESC-50 zip file not found at: {ZIP_ESC50_PATH}. Skipping ESC-50.")
        return

    extract_dir = os.path.join(BASE_DIR, "esc50_temp_dir")
    print("Extracting ESC-50...")
    with zipfile.ZipFile(ZIP_ESC50_PATH, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    csv_path = os.path.join(extract_dir, "ESC-50-master", "meta", "esc50.csv")
    audio_dir = os.path.join(extract_dir, "ESC-50-master", "audio")

    if not os.path.exists(csv_path):
        print("ESC-50 CSV meta-data file not found inside zip. Cleaning up.")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return

    # "fireworks" and "clock_alarm" are the closest real-audio proxies ESC-50
    # offers for explosion/fire_alarm — neither is a perfect match (no true
    # "explosion" or "fire alarm" category exists in ESC-50 or UrbanSound8K),
    # so treat their coverage as provisional, not equivalent to a dedicated
    # hazard recording.
    esc50_mapping = {
        "glass_breaking": "glass_breaking",
        "crying_baby": "shouting",
        "siren": "siren",
        "fireworks": "explosion",
        "clock_alarm": "fire_alarm",
    }

    # Real, unambiguous non-hazard ambience for the "normal" negative class.
    # Excludes anything acoustically close to a hazard class (e.g. thunder,
    # chainsaw, crackling_fire) to avoid teaching the model the wrong label
    # for a borderline sound.
    esc50_normal_categories = {
        "rain", "wind", "sea_waves", "water_drops", "insects", "chirping_birds",
        "crickets", "footsteps", "breathing", "pouring_water", "rooster", "hen",
        "cow", "sheep", "frog", "cat", "engine", "train", "airplane", "helicopter",
        "vacuum_cleaner", "washing_machine", "keyboard_typing", "mouse_click",
        "laughing", "coughing", "sneezing", "snoring", "brushing_teeth",
        "drinking_sipping", "toilet_flush", "door_wood_knock", "door_wood_creaks",
        "can_opening", "church_bells", "crow", "clock_tick",
    }
    max_per_normal_subclass = 20

    counts = {k: 0 for k in esc50_mapping.values()}
    counts["normal"] = 0
    normal_subclass_counts = {}
    processed_count = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row['category']
            filename = row['filename']

            target_class = None
            if category in esc50_mapping:
                target_class = esc50_mapping[category]
            elif category in esc50_normal_categories:
                if normal_subclass_counts.get(category, 0) >= max_per_normal_subclass:
                    continue
                target_class = "normal"
                normal_subclass_counts[category] = normal_subclass_counts.get(category, 0) + 1

            if target_class:
                source_path = os.path.join(audio_dir, filename)
                target_path = os.path.join(PROCESSED_DIR, target_class, f"esc50_{filename}")

                if os.path.exists(source_path):
                    if process_audio_file(source_path, target_path):
                        counts[target_class] += 1
                        processed_count += 1

    # Cleanup temp extraction folder
    print("Cleaning up ESC-50 temporary directories...")
    shutil.rmtree(extract_dir, ignore_errors=True)

    print(f"ESC-50 Ingestion Complete: processed {processed_count} files.")
    for target_class, count in counts.items():
        print(f"  - {target_class}: {count}")

AUGMENT_VARIANTS_PER_CLIP = 8
# "normal" already has ~740 real clips (37 ESC-50 ambient subclasses); every
# other real-audio class caps out at ESC-50's fixed 40 clips/category. Only
# the latter actually need more real-derived training/holdout data, and
# augmenting 740 normal clips would cost a lot of embedding time for almost
# no benefit.
AUGMENT_CLASSES = [c for c in ACTIVE_CLASSES if c not in ("normal", "gunshot", "scream")]


def _augment_waveform(audio, sr, rng):
    """Returns one randomly-augmented variant of a REAL recording.

    Pitch shift, time stretch, additive noise, gain jitter, and a single
    early reflection are standard, label-preserving audio augmentations --
    they change how a real recording sounds without inventing a new acoustic
    event, unlike generate_synthetic_data.py's from-scratch synthesis. That
    distinction is why augmented output still counts as externally-sourced
    evidence in model_readiness.py's _is_synthetic() check: it is a real
    recording, perturbed, not a fabricated one.
    """
    original_len = len(audio)
    out = audio.astype(np.float32).copy()

    if rng.random() < 0.7:
        steps = rng.uniform(-2.0, 2.0)
        out = librosa.effects.pitch_shift(y=out, sr=sr, n_steps=steps)

    if rng.random() < 0.5:
        rate = rng.uniform(0.9, 1.1)
        out = librosa.effects.time_stretch(y=out, rate=rate)

    # Restore the original length (pitch/time ops can change it slightly) so
    # every clip still fills the 5s Pass 2 verification window.
    if len(out) < original_len:
        pad = original_len - len(out)
        left = pad // 2
        floor = rng.normal(0, 0.003, original_len).astype(np.float32)
        floor[left:left + len(out)] = out
        out = floor
    elif len(out) > original_len:
        start = (len(out) - original_len) // 2
        out = out[start:start + original_len]

    if rng.random() < 0.8:
        signal_power = float(np.mean(out ** 2)) + 1e-9
        snr_db = rng.uniform(12, 28)
        noise_power = signal_power / (10 ** (snr_db / 10))
        out = out + rng.normal(0, noise_power ** 0.5, len(out)).astype(np.float32)

    gain = rng.uniform(0.6, 1.15)
    out = out * gain

    if rng.random() < 0.4:
        delay = int(sr * rng.uniform(0.02, 0.08))
        if 0 < delay < len(out):
            echo = np.zeros_like(out)
            echo[delay:] = out[:-delay]
            out = out + 0.25 * echo

    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out = out / peak * 0.9
    return out.astype(np.float32)


def _origin_id(filename):
    """Recovers the original real source-clip id an augmented file was
    derived from, so an augmented variant is always assigned to the SAME
    train/validation/test split as the recording it came from. Hashing the
    augmented filename directly (a different string per variant) would let
    the same underlying recording -- just perturbed -- land in both train
    and test, which is exactly the source leakage prepare_dataset.py's
    source-disjoint split exists to prevent."""
    match = re.match(r"^(esc50|us8k)aug_(.+)__v\d+(\.\w+)$", filename)
    if match:
        prefix, rest, ext = match.groups()
        return "{}_{}{}".format(prefix, rest, ext)
    return filename


def augment_real_audio(variants_per_clip=AUGMENT_VARIANTS_PER_CLIP, seed=17):
    """Expands every currently-real (ESC-50/UrbanSound8K) processed clip with
    label-preserving augmented variants. Must run after ingest_esc50()/
    ingest_urbansound8k() and before fill_missing_real_classes(), so it only
    ever touches genuine recordings -- gunshot and scream, which have no real
    source at all yet, are correctly left untouched (nothing real exists to
    augment) and still fall through to the synthetic fallback below.

    Why this exists: ESC-50 supplies exactly 40 real clips per hazard-proxy
    category, which is both a training-data and a holdout-size problem -- a
    3-6 clip test set makes any single precision/recall number close to
    meaningless. Augmenting the real recordings, source-disjointly, is a real
    accuracy and holdout-stability lever that needs no new dataset download.
    """
    print("\nAugmenting real-audio recordings ({} variants/clip, classes: {})...".format(
        variants_per_clip, ", ".join(AUGMENT_CLASSES)
    ))
    rng = np.random.default_rng(seed)
    total_written = 0
    for cls in AUGMENT_CLASSES:
        class_dir = os.path.join(PROCESSED_DIR, cls)
        if not os.path.exists(class_dir):
            continue
        source_files = sorted(
            f for f in os.listdir(class_dir)
            if f.endswith(".wav") and (f.startswith("esc50_") or f.startswith("us8k_"))
        )
        if not source_files:
            continue  # nothing real to augment yet for this class

        written_for_class = 0
        for source_name in source_files:
            source_path = os.path.join(class_dir, source_name)
            try:
                audio, sr = sf.read(source_path, dtype="float32")
            except Exception as error:
                print("  Skipping {}: could not read ({}).".format(source_name, error))
                continue
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)

            prefix = "esc50aug" if source_name.startswith("esc50_") else "us8kaug"
            stem = source_name.split("_", 1)[1]
            stem_noext, ext = os.path.splitext(stem)

            for variant in range(variants_per_clip):
                out_name = "{}_{}__v{:02d}{}".format(prefix, stem_noext, variant, ext)
                out_path = os.path.join(class_dir, out_name)
                if os.path.exists(out_path):
                    continue
                augmented = _augment_waveform(audio, sr, rng)
                sf.write(out_path, augmented, sr)
                written_for_class += 1
        total_written += written_for_class
        print("  {}: {} real clips -> +{} augmented".format(cls, len(source_files), written_for_class))
    print("Augmentation complete: wrote {} new real-derived clips.".format(total_written))


def fill_missing_real_classes():
    """Copies pre-generated synthetic clips for any class that still has zero
    real (processed) recordings after ingest_urbansound8k()/ingest_esc50()
    ran — e.g. because a real-audio source is temporarily unavailable
    (UrbanSound8K not downloaded yet) or because no clean real-audio proxy
    exists at all (see docs/SAFETY_IMPLEMENTATION_PLAN.md). This keeps every
    class trainable without disguising synthetic fallback as real evidence:
    model_readiness.py's per-class check independently verifies real coverage
    and will correctly refuse to call a synthetic-only class real-world ready,
    and will stop padding a class the moment real ingestion supplies it."""
    for cls in ACTIVE_CLASSES:
        dest_dir = os.path.join(PROCESSED_DIR, cls)
        has_real_data = os.path.exists(dest_dir) and any(
            f.endswith(".wav") for f in os.listdir(dest_dir)
        )
        if has_real_data:
            continue

        src_dir = os.path.join(SYNTHETIC_DIR, cls)
        if not os.path.exists(src_dir):
            print(f"No real or synthetic source found for '{cls}' at {src_dir}.")
            continue
        os.makedirs(dest_dir, exist_ok=True)
        copied = 0
        for wav_path in glob.glob(os.path.join(src_dir, "*.wav")):
            dest_path = os.path.join(dest_dir, f"synthetic_{os.path.basename(wav_path)}")
            if not os.path.exists(dest_path):
                shutil.copyfile(wav_path, dest_path)
                copied += 1
        print(f"'{cls}' has no real-audio source yet — copied {copied} synthetic fallback clips instead.")


def _source_dataset_for(filename):
    if filename.startswith("us8kaug_"):
        return "urbansound8k_augmented"
    if filename.startswith("esc50aug_"):
        return "esc50_augmented"
    if filename.startswith("us8k_"):
        return "urbansound8k"
    if filename.startswith("esc50_"):
        return "esc50"
    if filename.startswith("synthetic_"):
        return "synthetic_generated"
    return "unknown"


def _assign_split(source_clip_id):
    """Deterministic, source-disjoint 70/15/15 split. Hashing the source clip
    id (not a random shuffle) guarantees the same file always lands in the
    same split across runs, and that augmented copies of one source file
    can never straddle train/test."""
    bucket = int(hashlib.md5(source_clip_id.encode("utf-8")).hexdigest(), 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def generate_metadata_csv():
    print("\nGenerating final metadata.csv...")
    out_csv = os.path.join(PROCESSED_DIR, "metadata.csv")
    records = []

    for c in ACTIVE_CLASSES:
        class_dir = os.path.join(PROCESSED_DIR, c)
        if os.path.exists(class_dir):
            wav_files = glob.glob(os.path.join(class_dir, "*.wav"))
            for wav in wav_files:
                filename = os.path.basename(wav)
                source_dataset = _source_dataset_for(filename)
                split = _assign_split(_origin_id(filename))
                # Save as absolute path so train.py can easily load it from any Cwd
                records.append({
                    "filepath": os.path.abspath(wav),
                    "label": c,
                    "source_dataset": source_dataset,
                    "source_clip_id": filename,
                    "split": split,
                })

    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=["filepath", "label", "source_dataset", "source_clip_id", "split"]
        )
        writer.writeheader()
        writer.writerows(records)

    print(f"Dataset preparation complete! Compiled {len(records)} records in {out_csv}")
    print("\nClass Distribution Summary:")
    from collections import Counter
    dist = Counter([r["label"] for r in records])
    for cls in ACTIVE_CLASSES:
        print(f"  - {cls}: {dist.get(cls, 0)} files")

    manifest_result = validate_manifest(out_csv)
    if not manifest_result["valid"]:
        print("\nMANIFEST VALIDATION FAILED:")
        for blocker in manifest_result["blockers"]:
            print(f"  BLOCKER: {blocker}")
        raise RuntimeError("Generated metadata.csv failed manifest validation; refusing to hand it to train.py.")
    print("\nManifest validation passed: labels, splits, and source-disjointness are all consistent.")
    print(f"Split counts: {manifest_result['split_counts']}")


if __name__ == "__main__":
    setup_directories()
    ingest_urbansound8k()
    ingest_esc50()
    augment_real_audio()
    fill_missing_real_classes()
    generate_metadata_csv()
