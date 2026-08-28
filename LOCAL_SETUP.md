# Running Echo locally (Windows)

## TL;DR

```powershell
.\run_local.ps1 -Setup     # first time only: venv + deps + dataset + training (~5-10 min)
.\run_local.ps1            # every time after that
```

Then open <http://127.0.0.1:8010> — that is the web emulator (Demo Mode, live mic monitoring,
event history, contacts, nearby map). API docs: <http://127.0.0.1:8010/docs>.

Port 8010 is the default because port 8000 was already taken on this machine. Use
`-Port <number>` to change it.

## What `-Setup` does, and why each step is needed

1. **`.venv` + dependencies.** `requirements.txt` now installs `tensorflow` and
   `tensorflow-hub` directly (CPU-only wheels; no CUDA on this machine) — PyTorch/torchaudio
   are no longer used anywhere in this repo.
2. **`model/generate_synthetic_data.py`** — 400 procedurally generated clips (50 per class,
   8 classes) in `model/data/synthetic/`. The repo gitignores `model/data/` and
   `model/checkpoints/`, so a fresh clone has *no* audio and *no* model weights.
3. **`model/prepare_dataset.py`** — builds `model/data/processed/metadata.csv` (a full
   provenance manifest: filepath, label, source_dataset, source_clip_id, split). It ingests
   real ESC-50/UrbanSound8K audio for any class it can find a source for, and falls back to
   labeled synthetic clips (`synthetic_*.wav`) for any class that still has zero real audio
   afterward — currently gunshot and scream (see "Using real audio" below).
4. **`model/train_yamnet.py`** — downloads the pretrained YAMNet model from TF-Hub (frozen),
   extracts a mean+max-pooled embedding per clip, and trains a small classifier head on top.
   Writes `model/checkpoints/yamnet_head.keras`. `backend/main.py` calls `sys.exit(1)` at
   import time if this file is missing, so the backend cannot start without it.

## Using real audio instead of synthetic-only

```powershell
# ESC-50 (~600 MB, downloads automatically from GitHub)
cd model; ..\.venv\Scripts\python.exe prepare_dataset.py

# UrbanSound8K (~6 GB, NOT auto-downloaded -- Zenodo has repeatedly failed/dropped
# connection when attempted from this environment). To use it:
#   1. Download UrbanSound8K.tar.gz yourself (Kaggle mirror is far more reliable than
#      Zenodo direct: kaggle datasets download -d chrisfilo/urbansound8k)
#   2. Extract so model/data/raw/UrbanSound8K/UrbanSound8K.csv and .../fold1..fold10/ exist
#   3. Re-run prepare_dataset.py -- it picks UrbanSound8K up automatically
```

ESC-50 supplies real audio for: normal (ambient categories), explosion (fireworks proxy),
fire_alarm (clock_alarm proxy), glass_breaking, siren, shouting (crying_baby proxy).
UrbanSound8K is the only realistic free source for real gunshot audio. Neither dataset has a
clean "scream" match at all — see `docs/SAFETY_IMPLEMENTATION_PLAN.md` for what closing that
gap requires (FSD50K or consented recordings). `model/model_readiness.py` reports exactly
which classes are still synthetic-only; `model/evaluation_gates.py` refuses to call the model
release-ready until they aren't.

Demo Mode in the browser prefers `data/processed/<class>/<class>_esc50_000.wav` and falls back
to `data/synthetic/<class>/<class>_000.wav`.

## Emergency escalation (Telegram + automated voice call)

A verified high-risk detection now arms a countdown (default 12s), then calls and Telegram-
messages the user's saved contacts with the 5-second evidence clip, the class, risk score, and
location. Nothing is sent anywhere until you configure it:

```powershell
cd backend
copy .env.example .env
notepad .env      # TELEGRAM_BOT_TOKEN at minimum; TWILIO_* + ECHO_PUBLIC_BASE_URL for calls
```

Without `.env`, both channels run in **simulation mode**: the exact message/call script is
composed and logged (`GET /escalation/status` reports `simulation_mode: true`) but nothing
leaves the machine — the pipeline stays fully testable offline. Voice calls also need a public
URL (Twilio fetches the TwiML + clip from it), so use a tunnel in dev: `ngrok http 8010`.

Key endpoints: `POST /incidents` (arms the countdown), `POST /incidents/{id}/cancel` ("I'm
safe"), `GET /escalation/readiness/{user_id}` (a straight answer to "if something happened now,
who gets told"), `POST /escalation/test` (rehearsal alert, clearly labelled, to every contact).

## Demo model profile (Diwali firecracker -> gunshot alias)

For presentations, a second classifier head can be trained on real firecracker audio so the
full alert pipeline can be triggered live on stage without anyone needing a real gunshot. It
never touches the production head — see `model/model_profiles.py` for why that separation
matters.

```powershell
cd model
# Record 20-40 clips of the actual crackers you'll light, on the phone you'll present with,
# into model\data\raw\firecrackers\  (any common audio format). Falls back to ESC-50
# "fireworks" or synthetic audio if you skip this, but real recordings demo far better.
..\.venv\Scripts\python.exe prepare_demo_dataset.py
..\.venv\Scripts\python.exe train_yamnet.py --profile demo
```

Writes `model/checkpoints/yamnet_head_demo.keras`. Restart the backend and `GET /profiles`
reports `"demo": {"checkpoint_available": true}`. Switch to it in the app (Settings ->
Detection model, or the Demo tab's model switch) or pass `profile=demo` to `/detect` directly.
A firecracker detection is reported with `candidate: "gunshot"` (so the whole risk/escalation
path runs) and `raw_candidate: "firecracker"` (so nothing claims a real gunshot happened) —
every incident it creates is also stamped `profile: "demo"`.

## Mobile app (Flutter)

`app/` ships only `lib/` + `pubspec.yaml` — no `android/`/`ios/` folders, so `flutter run` has
nothing to build yet. One-time setup generates them and patches the mic/location/cleartext-HTTP
permissions the app needs:

```powershell
cd app
.\setup_app.ps1                                          # generates android/, ios/, flutter pub get
flutter run --dart-define=ECHO_API_URL=http://<lan-ip>:8010   # real phone, same Wi-Fi as the backend
flutter run                                                    # Android emulator (uses 10.0.2.2 by default)
```

The login screen accepts any email/password — see `app/lib/services/session_service.dart` for
why: it's a local identity (scopes contacts/history/incidents, and names the person in the
alert your contacts receive), not real authentication, and the UI says so.

## Tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest -q          # all endpoints + escalation, in-process
cd model;   ..\.venv\Scripts\python.exe -m pytest -q          # data manifest, gates, readiness,
                                                                # risk scorer, safety policy, YAMNet head,
                                                                # model profiles (real/demo taxonomy)
cd model;   $env:ECHO_API_URL="http://127.0.0.1:8010"; ..\.venv\Scripts\python.exe test_inference.py
cd model;   ..\.venv\Scripts\python.exe evaluate.py            # confusion matrix -> reports/
```

`test_inference.py` needs the server running; the others do not.

## Notes / honest caveats

- **Macro F1 is 0.95 on the current real+augmented-real+labeled-synthetic mix.** That clears the
  0.95 macro-F1 release gate for the first time, up from 0.85 -- `prepare_dataset.py` now also
  generates label-preserving augmented variants (pitch shift, time stretch, additive noise, gain
  jitter, a single early reflection) of every *real* ESC-50 recording, source-disjointly split so
  an augmented clip always lands in the same train/validation/test split as the recording it came
  from (see `_origin_id()`/`AUGMENT_CLASSES` in `prepare_dataset.py`). This is real-audio
  augmentation, not synthesis -- `model_readiness.py` correctly still counts it as external
  evidence, not synthetic. Gunshot and scream have zero real source clips to augment and remain
  100% synthetic-only (`model_readiness.py`'s per-class gate still correctly blocks on this; see
  `reports/evaluation_report.txt` for the exact remaining blockers -- currently explosion/
  fire_alarm/normal precision and explosion recall, plus the never-built playback-false-positive
  hard-negative evaluation). Run `evaluate.py` to reproduce the class-by-class numbers.
- **Risk scores escalate across consecutive detections** by design (`RiskScorer` keeps a
  sequential-event history), so hitting several Demo Mode buttons in a row raises the level.
- **Microphone mode** needs browser permission; `http://127.0.0.1` counts as a secure context
  so Chrome/Edge will allow it.
- **`/nearby`** calls the public OSM Overpass API. It is frequently rate-limited/overloaded and
  the endpoint silently falls back to two mock locations (`"status": "fallback"`).
- **The Flutter app in `app/`** targets a phone, not the browser, and there is no Flutter SDK
  installed on this machine to run `flutter analyze`/`flutter run` here — the backend
  integration it talks to (`/detect`, `/incidents`, `/contacts`, `/profiles`, `/escalation/*`)
  was verified end-to-end via FastAPI's `TestClient` instead (see `backend/test_emergency.py`
  and the ad-hoc `/detect` smoke test in the commit that added the escalation layer). The app
  is now the primary surface (login, light theme, escalation countdown, demo model switch);
  `backend/static/` remains the older browser prototype and was not updated to match.
- **Export scripts** (`export_tflite.py`, `export_openvino.py`, `benchmark_openvino.py`) work
  in this environment — `tensorflow`, `tensorflow-hub`, and `openvino` install cleanly and the
  exported `.tflite`/OpenVINO IR files have been verified to run real inference, not just
  export without error.
- **Movie/TV gunshot scenario**: media-playback suppression works two ways now. The manual
  toggle (Home screen / browser "Media playback" checkbox) still works as before. In addition,
  `model/audio_classes.py` reads YAMNet's own general AudioSet predictions (Television, Music,
  Soundtrack music, etc.) as a weak automatic signal — if it fires without the user having
  toggled anything, the response's `acoustic_media_detected` field is `true` so the UI can show
  *why* an alert was suppressed instead of silently downgrading it. Either signal only lowers
  urgency to a reviewable state; it never silently drops a verified event, and conflicting
  evidence (sudden motion, a repeat hazard sequence) still forces an alert.

## Fixes applied while completing the emergency-escalation + accuracy pass

- `evaluate.py`, `export_tflite.py`, `export_openvino.py` imported `EMBEDDING_CACHE_PATH`/
  `HEAD_CHECKPOINT_PATH`/`MANIFEST_PATH` from `train_yamnet`, module-level constants that no
  longer existed after the `model_profiles.py` refactor (`train_yamnet._paths_for(profile)`
  replaced them). All three were `ImportError`-broken and silently uncovered by the test suite.
  Fixed to use `_paths_for()`/`get_profile()`, and all three now accept `--profile`.
- `backend/emergency.py`'s Telegram/voice messages sent a client-supplied placeholder
  (`"Last known location"`) as the location label. `backend/geocode.py` now resolves a real
  street-level address from lat/lng via OSM Nominatim (free, no key, same no-key philosophy as
  `/nearby`'s Overpass calls) at dispatch time, and persists it onto the incident.
- `POST /escalation/test` had no rate limit at all (unlike `/incidents`, which is protected by
  `escalation_gate()`'s cooldown) -- a rehearsal endpoint that dials real phone numbers with zero
  cap on repeat calls. Added a per-user sliding-window limiter (`emergency_routes.py`).
- `backend/static/`'s `.chat-picker` and `.wav-btn` CSS rules set `display` unconditionally,
  which -- at equal specificity -- beats the browser's default `[hidden] { display: none }` rule
  (author-stylesheet rules always win over the user-agent stylesheet, regardless of specificity
  ties). Both elements rendered even while `hidden`. Fixed with `:not([hidden])` guards.

## Fixes applied while getting this to run

- `model/test_model.py` imported `EchoCRNN`, which no longer exists (the class was renamed
  `EchoTransformer`), and fed a 64-bin dummy input where the model expects 192 bins.
- `backend/main.py` Pass 2 derived its Pass 1 window as a fixed 2/5 slice of the uploaded
  audio, which silently shrank the window for clips that were not exactly 5s and caused
  systematic misclassification. It now takes a real 2-second window.
- `backend/main.py` `/nearby` sent no `User-Agent`; Overpass answers those with HTTP 406, so
  the endpoint always fell back to mock data. It now identifies itself and retries on 504.
- `model/generate_synthetic_data.py` produced 2–4s clips, so the 5s Pass 2 verification window
  was mostly zero-padding and verification failed for 6 of 8 classes. Clips are now ~5s.
- `model/test_inference.py` hardcoded port 8000 and only looked in `data/processed`; it now
  honours `ECHO_API_URL` and falls back to the synthetic clips.
- `requirements.txt` was missing every backend dependency (fastapi, uvicorn, python-multipart,
  soundfile, requests, scikit-learn, httpx2).

## Architecture change: CNN-Transformer -> YAMNet transfer learning

The model was replaced end-to-end: `model.py` (custom CNN-Transformer), `dataset.py`
(log-mel + Sobel/Laplacian spectrogram pipeline), and the from-scratch `train.py` were deleted.
See `docs/DECISIONS_LOG.md` entry #8 for why and what changed.
