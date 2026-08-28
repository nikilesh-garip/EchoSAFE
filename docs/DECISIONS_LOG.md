# ECHO — Decisions Log (Master Context Pack, Part 3 of 5)

> Append-only. Never delete an entry, even if reversed — add a new entry that supersedes it.
> Every AI-assisted session that changes an architectural/scope decision MUST result in a new
> entry here, written by the human who approved the change, same day. If it's not written down
> here, treat it as not decided — revert to what ARCHITECTURE.md/PROJECT_BRIEF.md already say.

Format per entry:
```
### #N — [short title]
Date:
Decided by:
What: (one line)
Why: (one line)
Affects: (which file(s) also needed updating)
```

---

### #1 — Session-based monitoring instead of 24/7 background
Date: [fill in]
Decided by: team
What: Monitoring runs while app is foregrounded/active service, not persistent 24/7 OS-level.
Why: Android 13+ background mic restrictions + Doze mode make true 24/7 unreliable to build
in timeframe; output/UX unaffected (same ON/OFF toggle).
Affects: PROJECT_BRIEF.md, ARCHITECTURE.md

### #2 — Single CRNN, two-pass, instead of two separate model architectures
Date: [fill in]
Decided by: team
What: Replaced AST/PANNs/CLAP "verification model" with the same CRNN run twice at different
window sizes/thresholds.
Why: Heavy transformer models need cloud inference, which conflicts with the no-continuous-
audio-upload privacy rule, and are impractical to train from scratch in timeframe.
Affects: ARCHITECTURE.md

### #3 — Keyword-spotter instead of full ASR
Date: [fill in]
Decided by: team
What: Replaced Whisper/general ASR with a small grammar-constrained keyword spotter for ~6
fixed phrases.
Why: Full ASR is a separate heavy subsystem for a "supporting evidence only" signal; not
worth the engineering cost at this scope. Tier 2 — cut first if behind schedule.
Affects: ARCHITECTURE.md, PROJECT_BRIEF.md

### #4 — Nearby-device alerts fully simulated
Date: [fill in]
Decided by: team
What: No real device-to-device networking; Demo Mode calls a mocked backend endpoint with
scripted "corroboration" data.
Why: Real implementation needs user density + background location infra not available at
prototype scale; explicitly Tier 3, disclosed in report.
Affects: ARCHITECTURE.md, TIER_TABLE.md

### #5 — Post-training quantization + OpenVINO instead of pruning/QAT
Date: [fill in]
Decided by: team
What: Use TFLite post-training dynamic-range quantization for mobile export; OpenVINO IR
export for laptop-side (Intel Arc iGPU) latency/size benchmarking.
Why: Pruning/QAT requires specialized ML-systems expertise beyond scope/timeline; OpenVINO
benchmarking on team's actual Intel hardware is a stronger, more specific interview story
than generic TFLite-only claims.
Affects: ARCHITECTURE.md

---

<!-- Add new entries below this line as the project progresses. -->

### #9 — Real-audio augmentation to close the macro-F1 gate; escalation location + rate limiting
Date: August 27, 2026
Decided by: team (AI-assisted)
What: `prepare_dataset.py` now generates label-preserving augmented variants (pitch shift, time
stretch, additive noise, gain jitter, one early reflection) of every real ESC-50 recording for
explosion/glass_breaking/fire_alarm/siren/shouting, source-disjointly split so an augmented clip
always lands in the same split as its source recording -- never both train and test. Macro F1
went 0.85 -> 0.9508 (clears the 0.95 gate for the first time); `synthetic_generated` gunshot/
scream sample counts and generator realism were also increased, but those two classes remain
100% synthetic (no augmentation possible with zero real source clips). Fixed a real bug: three
scripts (`evaluate.py`, `export_tflite.py`, `export_openvino.py`) had been `ImportError`-broken
since the profile refactor (entry #8) and silently uncovered by the test suite -- both are now
fixed and covered by a live run, not just an import check. Also added: `backend/geocode.py`
(OSM Nominatim reverse geocoding for the escalation call/Telegram location line, no API key),
a per-user rate limit on `/escalation/test` (previously uncapped -- unlike `/incidents`, it
skipped `escalation_gate()`'s cooldown entirely), and a redesigned `backend/static/` dashboard
(risk-level color coding, an animated escalation countdown ring, toast notifications, a "send a
real test alert" button, and full per-contact Telegram/priority/channel-opt-out fields that were
previously Flutter-app-only). See `reports/evaluation_report.txt` for the exact remaining release
blockers -- explosion/fire_alarm/normal precision, explosion recall, and gunshot/scream's
synthetic-only status are all still honestly gated, not overridden.
Affects: model/prepare_dataset.py, model/generate_synthetic_data.py, model/evaluate.py,
model/export_tflite.py, model/export_openvino.py, backend/geocode.py (new), backend/emergency.py,
backend/notifiers.py, backend/emergency_routes.py, backend/static/, LOCAL_SETUP.md.

### #6 — CNN-Transformer with Spatial Derivative Features
Date: July 24, 2026
Decided by: team
What: Upgraded the sound classification model to a CNN-Transformer architecture and added spatial Mel-spectrogram derivatives (Sobel and Laplacian) as input features.
Why: Outperforms baseline CRNN in modeling long-term temporal dependencies in parallel, improving F1 score to 93.58% and accuracy to 96.59% while reducing noise sensitivity.
Affects: model/model.py, model/dataset.py, model/two_pass_detector.py, model/train.py, model/evaluate.py

### #7 — Immediate Verification for Transient Hazard Classes
Date: July 24, 2026
Decided by: team
What: Bypassed the 5-second Pass 2 recording delay for transient classes (gunshot, explosion, glass breaking), triggering instant emergency warnings on Pass 1.
Why: Gunshots and explosions are non-repeating impulses that do not persist into a subsequent recording block. Requiring a second recording block is unsafe for single-event threats.
Affects: backend/main.py, backend/static/app.js

### #8 — Replaced from-scratch CNN-Transformer with a fine-tuned YAMNet head
Date: August 17, 2026
Decided by: team (AI-assisted)
What: Deleted model.py (CNN-Transformer), dataset.py (log-mel + Sobel/Laplacian preprocessing),
and the from-scratch train.py. Replaced with model/train_yamnet.py: a frozen, pretrained
YAMNet backbone (TF-Hub) + a small trainable classifier head on mean+max-pooled embeddings.
Why: Real-audio coverage per class is thin (zero to ~740 clips) and a transformer trained from
zero on that little real data either overfits or fails to generalize. YAMNet was pretrained on
~2M AudioSet clips, so the head needs far fewer real examples to generalize well. This also
solves the CNN-Transformer's permanently-blocked TFLite export (ai-edge-torch has no build for
this Python version; the onnx-tf fallback is unmaintained/incompatible) since a Keras model
converts to TFLite/OpenVINO natively. Measured result on the same expanded real+labeled-
synthetic dataset: macro F1 0.82 (CNN-Transformer) -> 0.85 (YAMNet head) — a real improvement,
not release-ready either way (see reports/evaluation_report.txt, evaluation_gates.py).
Also added: an automatic "acoustic media-context" signal read from YAMNet's own general
AudioSet predictions (Television, Music, Soundtrack music, etc.), feeding the existing
media_playback/safety_policy pipeline as a new, weaker context_source tier
("acoustic_signal") alongside the pre-existing manual/platform_signal tiers — this is what
makes the "gunshot during a movie" scenario resolve automatically, not only via the manual
toggle. It never overrides an explicit signal and never silently drops a verified event.
Affects: model/ (new: audio_classes.py, yamnet_features.py, train_yamnet.py; rewritten:
two_pass_detector.py, evaluate.py, export_tflite.py, export_openvino.py, benchmark_openvino.py,
safety_policy.py; removed: model.py, dataset.py, train.py, generate_real_metadata.py,
ingest_real_datasets.py), backend/main.py, docs/ARCHITECTURE.md, docs/YAMNET_MODEL.md
(replaces docs/TRANSFORMER_MODEL.md), docs/TIER_TABLE.md, docs/PROJECT_BRIEF.md,
requirements.txt, app/lib/screens/settings_screen.dart, backend/static/index.html.

