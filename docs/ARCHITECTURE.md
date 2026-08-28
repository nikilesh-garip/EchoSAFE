# ECHO — Architecture (Master Context Pack, Part 2 of 5)

> Paste alongside PROJECT_BRIEF.md. This file is the technical contract between team members
> and between AI tools. If you (or an AI tool) want to change something here, that change goes
> through DECISIONS_LOG.md first, then this file gets updated, then everyone is told.
>
> [PLACEHOLDER: Once papers are uploaded, the model section below will be updated with
> specific layer configs / augmentation methods drawn from the papers. Until then, use the
> defaults below.]

## Repo Structure (everyone builds inside this — no personal variants)

```
/echo-project
  /docs
    PROJECT_BRIEF.md
    ARCHITECTURE.md          <- this file
    DECISIONS_LOG.md
    TIER_TABLE.md
    CODING_CONVENTIONS.md
    TEAM_ROLES.md
  /model
    /data                    <- raw + processed datasets (gitignored, documented in DATASET_TABLE.md)
    /notebooks               <- exploration only, nothing production depends on notebooks
    train.py
    model.py                 <- CNN-Transformer definition, single source of truth for architecture
    dataset.py               <- data loading, augmentation
    export_tflite.py
    export_openvino.py
    evaluate.py              <- confusion matrix, precision/recall/F1, FPR/FNR
  /app                       <- mobile app
    /src
  /backend                   <- FastAPI
    /routes
    /models                  <- Pydantic schemas (NOT ML models — name carefully to avoid confusion)
  /demo_assets
    /audio_clips             <- the 9 demo scenario files
    demo_script.md           <- what to say/click for each scenario during panel demo
  /reports
```

## Model Architecture (YAMNet transfer learning — Tier 1, Person A's deep-dive)

**Input:** raw 16kHz mono waveform, 2-5s. See `docs/YAMNET_MODEL.md` for the full writeup and
`docs/DECISIONS_LOG.md` entry #8 for why this replaced the original from-scratch
CNN-Transformer.

**Architecture:**
```
Waveform (16kHz mono)
-> YAMNet (frozen, pretrained on ~2M AudioSet clips, TF-Hub "google/yamnet/1")
   -> per-frame 1024-d embeddings (0.96s windows, 0.48s hop) + 521-class AudioSet scores
-> mean-pool embeddings across frames, max-pool embeddings across frames, concatenate (2048-d)
-> BatchNorm -> Dense(128, L2) -> Dropout(0.3) -> Dense(8, softmax)
```
Only the final block is trained; YAMNet itself stays frozen. This trades from-scratch model
capacity for sample efficiency, which matters when real per-class audio ranges from zero to a
few hundred clips.

**Two-pass "verification" (replaces separate Model A/B):**
- Pass 1 ("Primary"): 2s window, threshold 0.5 to trigger Pass 2.
- Pass 2 ("Verification"): 5s window centered on the same event, threshold 0.7 for final
  hazard confirmation. Report both numbers on the alert screen exactly as originally specced.

**Automatic media-context signal:** each pass also reads YAMNet's own general AudioSet
predictions (Television, Music, Soundtrack music, Radio, etc.) as a weak, automatically
detected acoustic signal that a movie/TV/game is likely playing — feeding the same
`media_playback` context input as the manual toggle, at a distinct, lower-reliability tier
(`context_source="acoustic_signal"`). See `model/audio_classes.py` and
`model/safety_policy.py`. It only ever adds evidence; it never overrides an explicit `False`,
and conflicting evidence (sudden motion, a repeat hazard sequence) still forces an alert.

**Training:** TensorFlow/Keras. Class-weighted (inverse-frequency) cross-entropy — "normal"
outnumbers hazard classes roughly 15-to-1 in the current dataset.

**Export:** `export_tflite.py` builds one combined graph (YAMNet + pooling + head) and converts
it directly to a quantized `.tflite` (~3.5MB, verified to run real inference). `export_openvino.py`
produces IR format for laptop-side latency/size benchmarking (Person A's OpenVINO-on-Arc-iGPU
story — this is the differentiator, don't skip it).

## Context/Risk Scorer (Tier 1, heuristic — Person C)

Weighted sum, NOT a black box. Documented formula lives in `model/risk_scorer.py` as a
config dict, e.g.:

```python
WEIGHTS = {
    "primary_confidence": 0.35,
    "verification_confidence": 0.35,
    "media_playback_active": -0.25,   # negative = reduces risk
    "sudden_motion_detected": 0.15,
    "repeated_impulse_count": 0.10,   # per repeat, capped
}
THRESHOLDS = {"NORMAL": 30, "SUSPICIOUS": 60, "POSSIBLE_DANGER": 80, "HIGH_RISK": 100}
```
Every number in this dict must be justifiable out loud in a viva. Don't let an AI tool bury
this logic inline somewhere else — it stays in one file, one function, one truth.

## Keyword Spotter (Tier 2 — simplified, cut first if behind schedule)

Small grammar-constrained recognizer (e.g., Vosk small model with a fixed phrase list) for:
"help me", "call the police", "leave me alone", "don't hurt me", "call an ambulance", "fire".
Output is a boolean-per-phrase signal fed into the risk scorer as supporting evidence only —
never a standalone trigger.

## Backend API Contract (FastAPI — Person B)

```
POST /events                 -> log a detection event (metadata only, never raw audio)
GET  /events/{user_id}        -> history for HISTORY screen
POST /contacts                -> CRUD emergency contacts
GET  /nearby?lat&lng&type     -> proxy to Places API (police/hospital/fire)
POST /demo/nearby-corroboration (Tier 3, mocked)  -> returns scripted nearby-device data
```
No endpoint accepts or stores raw continuous audio. Ever. This is a privacy hard-line, not a
style preference — see PROJECT_BRIEF.md.

## Mobile App Screens (per original spec, unchanged)

HOME, LIVE MONITOR, ALERT, HISTORY, CONTACTS, SETTINGS, DEMO MODE. See original spec sections
18/16/13 for exact layout — that part of the spec was fine, keep it as-is.

## Demo Mode Mechanics (Tier 1, critical for panel)

Audio files in `/demo_assets/audio_clips`, played through device speaker into the mic OR
injected directly into the inference pipeline as a file input (bypass mic if speaker playback
proves unreliable in the room — document this fallback, don't hide it). Must visually show
each pipeline stage per the original spec's Section 16 example format.
