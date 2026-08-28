# ECHO — YAMNet Transfer-Learning Model

Replaces the earlier from-scratch CNN-Transformer (see `docs/DECISIONS_LOG.md` entry #8 for
why). This document describes the current model as actually implemented in `model/`.

---

## 1. Why transfer learning instead of training from scratch

The real bottleneck for this project is data, not model capacity: real-audio coverage per
hazard class ranges from zero (gunshot, scream — synthetic-only) to ~740 clips (normal) to
~40 clips (explosion, fire_alarm, glass_breaking, siren, shouting). A transformer trained from
zero on a few dozen real examples per class has no prior knowledge of what audio in general
sounds like; it either overfits or fails to generalize.

YAMNet (`google/yamnet/1`, TF-Hub) was pretrained on ~2M labeled AudioSet clips across 521
general sound categories. Freezing it and training only a small classifier head on its
embeddings needs far fewer real examples per class to generalize, because the head only has to
learn to re-combine an already-rich, general-purpose audio representation — not learn what
audio structure looks like from zero.

## 2. Feature extraction (`model/yamnet_features.py`)

YAMNet takes a raw 16kHz mono waveform directly — it does its own internal STFT/mel-spectrogram
framing (0.96s windows, 0.48s hop), so there is no separate spectrogram-preprocessing step like
the old CNN-Transformer's log-mel + Sobel/Laplacian pipeline.

For each clip:
1. Run YAMNet, producing one 1024-d embedding and one 521-class AudioSet probability vector
   per ~0.96s frame.
2. **Mean-pool** across frames — the clip's average acoustic character.
3. **Max-pool** across frames — the single most salient frame, which matters for transient
   hazard sounds (a gunshot or glass break is often 1-2 of many frames, the rest near-silence;
   mean-pooling alone measurably hurt these classes during tuning — see commit history).
4. Concatenate mean + max into a 2048-d embedding.

## 3. Classifier head (`model/train_yamnet.py`)

```
Input: 2048-d [mean | max] embedding
BatchNormalization
Dense(128, activation=relu, L2=1e-3)
Dropout(0.3)
Dense(8, activation=softmax)
```

Trained with class-weighted (inverse-frequency) `sparse_categorical_crossentropy` — "normal"
outnumbers hazard classes roughly 15-to-1 in the current dataset, and without weighting the
head could minimize loss by mostly predicting "normal," which is the wrong failure mode for a
safety alarm. Early stopping and checkpointing both monitor `val_accuracy`, not `val_loss` —
crossentropy on a ~158-example validation set is spiky enough (a few hard examples swing it a
lot) that accuracy is the more reliable stopping signal at this sample size.

## 4. Current real evaluation result

Run `python evaluate.py` for the live numbers; do not trust any number here as current without
re-running it. As of the last training run on the real+labeled-synthetic mix described in
`docs/SAFETY_IMPLEMENTATION_PLAN.md`:

- Macro F1: **0.85** (release gate: 0.95 — not met)
- Overall accuracy: **0.93**
- `model/evaluation_gates.py` correctly reports `release_ready: False` with the specific
  per-class blockers still open (see the report for the current list).

This is a real, honest number on a held-out, source-disjoint test split — not the earlier
CNN-Transformer's 1.0 F1, which was an artifact of a trivial synthetic-only test set. It is
also an improvement over the CNN-Transformer's F1 of 0.82 on the same expanded real+synthetic
data, consistent with the sample-efficiency argument in section 1 — but it is still not
release-ready, and closing that gap needs more real audio, not more head tuning.

## 5. Two-pass detection and the acoustic media-context signal

Pass 1 (2s, threshold 0.50) / Pass 2 (5s, threshold 0.70) logic is unchanged from before — see
`model/two_pass_detector.py`. New: each pass also reports an automatically-detected
**acoustic media-context score**, read from YAMNet's own general 521-class predictions for
labels like "Television," "Music," "Soundtrack music," and "Radio" (see
`model/audio_classes.py`'s `MEDIA_CONTEXT_AUDIOSET_INDICES`). This is what makes the
"gunshot during a movie" scenario work automatically, not just via the user's manual toggle:

- It is treated as weak evidence, same tier as the `platform_signal` context source already
  defined in `safety_policy.py` — never proof, and never able to silently drop a verified
  event on its own (see `docs/SAFETY_IMPLEMENTATION_PLAN.md`'s "Gunshot versus playback"
  section, and `model/test_safety_policy.py`'s `test_movie_gunshot_scenario_*` tests).
- Conflicting evidence (sudden motion, a repeated hazard sequence) still forces an alert even
  if the acoustic signal fires.
- The backend's `/detect` response includes `acoustic_media_score` and
  `acoustic_media_detected` so the UI can disclose *why* an alert was suppressed, instead of
  silently downgrading it.

## 6. Export

`export_tflite.py` and `export_openvino.py` both build one combined graph — YAMNet
(`hub.KerasLayer`, frozen) + mean/max pooling + the trained head — and convert that directly.
Both have been verified to produce a file that runs real inference (not just "exports without
error"): the TFLite model classifies a gunshot clip correctly at ~3.5MB total, and the OpenVINO
IR model produces a valid softmax output on CPU. This replaces the CNN-Transformer's export
path, which was permanently blocked in this environment (ai-edge-torch does not support this
Python version; the onnx-tf fallback is unmaintained and incompatible with current onnx).
