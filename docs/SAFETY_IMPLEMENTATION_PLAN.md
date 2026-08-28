# Echo safety implementation plan

## Safety boundary

Echo must never claim that audio alone proves a crime, a fire, or a real gunshot.
It may notify a user, preserve metadata, present guidance, and offer a user-initiated
emergency handoff. It must not automatically call or dispatch police, fire, or medical
services from a model result.

## Implemented foundation

1. **Conservative decision policy**: verified events are categorized as monitoring,
   likely-playback review, review-now, urgent-user-action, or log-only.
2. **Truthful readiness endpoint**: `GET /readiness` reports local data composition and
   blocks deployment readiness when training/evaluation data is synthetic-only.
3. **User-visible escalation**: the browser requests notification permission while
   monitoring, notifies only for urgent user action, offers a `tel:112` handoff, and
   can export an incident report containing metadata and policy rationale.
4. **Complete confirmed-event history**: playback-suppressed verified events are logged
   for review; they are not silently dropped just because they did not interrupt the user.

## Model-accuracy work required before any real-world claim

### Dataset and split — current status

- `model/data_manifest.py` now enforces the provenance/split contract described below
  (required columns, valid splits, one source clip in exactly one split) and
  `prepare_dataset.py` refuses to hand `train.py` a manifest that fails it.
- ESC-50 is ingested for real audio: glass_breaking, siren, shouting (crying_baby proxy),
  and — new, provisional — explosion (fireworks proxy) and fire_alarm (clock_alarm proxy).
  Neither proxy is a true match; treat their gates as unmet until FSD50K or a consented
  recording set supplies real explosion/fire-alarm audio. ESC-50's ambient categories
  (rain, wind, footsteps, engine, etc., capped per subcategory) now back the "normal"
  negative class with real recordings instead of synthetic white noise alone.
  Gunshot and scream still have no ESC-50/UrbanSound8K equivalent.
- UrbanSound8K (the only realistic free source for real gunshot audio) could not be
  downloaded in a working session: Zenodo serves it at roughly 0.7 MB/s and the connection
  dropped mid-transfer at ~780 MB of 6 GB. `prepare_dataset.py` self-heals around this —
  any class still missing real coverage after ingestion falls back to labeled synthetic
  clips (`synthetic_*` filenames) rather than blocking the pipeline — but gunshot and
  scream remain synthetic-only until that download completes on a connection that can
  sustain it, or FSD50K / a consented recording set is used instead.
- `model/model_readiness.py` now checks real-audio coverage **per class**, not just in
  aggregate — a class with only synthetic clips is reported as a named blocker even when
  other classes in the same tree have real recordings. This is what actually enforces the
  "replace synthetic-only training" rule below at gate level, not just in this document.
- Record source, source clip ID, device, environment, and augmentation lineage in a
  manifest. Split by source clip, not random windows, to prevent source leakage.
  (Implemented: `prepare_dataset.py` assigns a deterministic, hashed, source-disjoint
  70/15/15 split per clip; `train.py` reads that split instead of re-shuffling.)
- Still to do: license/ingest FSD50K for a real "scream" class and a cleaner
  explosion/fire_alarm source; build the hard-negative set (films/TV/game audio, door
  slams, fireworks, construction, dishes, balloons, crowd noise, music, vehicle backfire,
  device-speaker playback); collect a consented smartphone-domain holdout set.
- Keep a locked, never-trained-on smartphone holdout set and report per-class precision,
  recall, false-positive rate, false-negative rate, and confidence calibration.

### Acceptance gates

Do not deploy or describe the model as safety-ready until all target classes meet
pre-agreed holdout targets on unseen device/environment recordings and the evaluation
includes movie/game and common-impact negatives. Thresholds must be chosen from the
holdout set, not from demo clips.

### Gunshot versus playback

Audio classification alone cannot prove whether a gunshot originated in the room or
from a movie. Use playback state only as evidence:

- Browser: manual user declaration only; label it `manual`.
- Android native app: optional AudioPlaybackCapture signal after user consent, where
  the source app permits capture; label it `platform_signal`.
- iOS native app: audio-session state can indicate other playback, but not identify
  the content source; label it `platform_signal` with lower confidence.
- Any playback signal plus sudden motion, a hazard sequence, or high-risk evidence
  remains an urgent user-action state.

## Emergency handoff

- India: make a user-tapped `tel:112` call available with visible location and incident
  summary. The official 112 India app remains the correct path for platform-supported
  location-aware emergency requests.
- Trusted contacts: add explicit, opt-in SMS/push delivery with a delivery receipt.
- Police/ambulance API dispatch is out of scope unless a specific agency provides an
  approved integration, data contract, consent flow, audit requirements, and test
  environment. Never simulate a successful dispatch.

## Platform delivery order

1. Finish browser prototype and validation tools.
2. Make the Flutter Android app the mobile implementation: actual rolling `AudioRecord`,
   foreground-service behavior, permissions, geolocation, and native playback context.
3. Add iOS support with its more limited playback signal.
4. Run controlled field testing with consent and a safety review before public release.
