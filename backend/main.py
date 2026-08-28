import os
import sys
import time
import uuid
import sqlite3
from contextlib import asynccontextmanager
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path so we can import model modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model")))

from two_pass_detector import TwoPassDetector
from risk_scorer import RISK_CONFIG, RiskScorer
from safety_policy import decide_action
from model_readiness import assess_dataset_readiness
from audio_classes import MEDIA_CONTEXT_THRESHOLD
from model_profiles import DEMO_PROFILE_NAME, REAL_PROFILE_NAME, available_profiles, get_profile
from yamnet_features import load_yamnet

import emergency_routes
from db import DB_PATH, get_db, init_db


def _resolve_media_context(client_media_playback, client_context_source, acoustic_media_score):
    """Combines the user/platform-reported media_playback flag with the
    automatically-detected acoustic media-context signal (see
    audio_classes.MEDIA_CONTEXT_AUDIOSET_INDICES). The acoustic signal only
    ever adds evidence of playback -- it never overrides an explicit False,
    and it is tagged with its own, weaker context_source so safety_policy's
    context_reliability field stays honest about where the signal came from.
    """
    if client_media_playback:
        return True, client_context_source
    if acoustic_media_score >= MEDIA_CONTEXT_THRESHOLD:
        return True, "acoustic_signal"
    return False, client_context_source


DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model", "data"))

init_db()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    emergency_routes.start_sweeper()
    yield


app = FastAPI(title="Echo Smart Emergency System API", version="2.0", lifespan=_lifespan)

# Initialize Detectors and Scorer (Fail fast on startup if the production
# checkpoint is missing or corrupt). The demo head is optional: a machine that
# never runs the presentation should still start.
REAL_PROFILE = get_profile(REAL_PROFILE_NAME)
DEMO_PROFILE = get_profile(DEMO_PROFILE_NAME)

if not REAL_PROFILE.checkpoint_exists:
    print("CRITICAL: Model checkpoint missing at: {}".format(REAL_PROFILE.checkpoint_path))
    sys.exit(1)

detectors = {}
try:
    # One frozen YAMNet backbone shared by both heads -- loading it twice would
    # cost ~30s and several hundred MB for identical weights.
    shared_yamnet = load_yamnet()
    detectors[REAL_PROFILE_NAME] = TwoPassDetector(profile=REAL_PROFILE, yamnet=shared_yamnet)
    print("Successfully loaded YAMNet transfer-learning classifier for inference!")
except Exception as e:
    print("CRITICAL ERROR loading model: {}".format(e))
    sys.exit(1)

if DEMO_PROFILE.checkpoint_exists:
    try:
        detectors[DEMO_PROFILE_NAME] = TwoPassDetector(profile=DEMO_PROFILE, yamnet=shared_yamnet)
        print("Demo profile head loaded (firecracker class available).")
    except Exception as e:
        # A broken demo head must never take down the production path.
        print("WARNING: demo head present but failed to load: {}".format(e))
else:
    print("Demo profile head not built yet (run prepare_demo_dataset.py + "
          "train_yamnet.py --profile demo).")

detector = detectors[REAL_PROFILE_NAME]  # backwards-compatible alias
scorer = RiskScorer()

app.include_router(emergency_routes.router)


# Pydantic Schemas
class EventCreate(BaseModel):
    user_id: str
    class_name: str
    primary_conf: float
    verification_conf: float
    risk_score: int
    risk_level: str

class EventResponse(BaseModel):
    id: int
    user_id: str
    timestamp: float
    class_name: str
    primary_conf: float
    verification_conf: float
    risk_score: int
    risk_level: str

class ContactCreate(BaseModel):
    user_id: str
    name: str
    phone: str
    relation: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    priority: Optional[int] = 100
    notify_call: Optional[bool] = True
    notify_telegram: Optional[bool] = True

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    relation: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    priority: Optional[int] = None
    notify_call: Optional[bool] = None
    notify_telegram: Optional[bool] = None

class ContactResponse(BaseModel):
    id: int
    user_id: str
    name: str
    phone: str
    relation: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    priority: Optional[int] = 100
    notify_call: Optional[bool] = True
    notify_telegram: Optional[bool] = True


def _get_detector(profile_name):
    try:
        profile = get_profile(profile_name)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if profile.name not in detectors:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model profile '{}' is not loaded on this backend. Build it with "
                "`python prepare_demo_dataset.py` then "
                "`python train_yamnet.py --profile {}`.".format(profile.name, profile.name)
            ),
        )
    return detectors[profile.name], profile


@app.get("/profiles")
def list_profiles():
    """Which classifier heads this backend can serve, and which are loaded."""
    profiles = available_profiles()
    for entry in profiles:
        entry["loaded"] = entry["name"] in detectors
    return {"active_default": REAL_PROFILE_NAME, "profiles": profiles}


@app.post("/detect")
async def detect_audio(
    file: UploadFile = File(...),
    duration: float = Form(..., description="Duration of the audio clip in seconds"),
    media_playback: bool = Form(False, description="Whether media is playing on device"),
    sudden_motion: bool = Form(False, description="Whether sudden motion is active"),
    primary_candidate: Optional[str] = Form(None, description="Candidate retained from pass 1"),
    primary_confidence: Optional[float] = Form(None, description="Confidence retained from pass 1"),
    sensitivity_threshold: float = Form(0.50, description="Pass 1 candidate threshold"),
    user_id: str = Form("anonymous", description="Monitoring session identifier"),
    context_source: str = Form("browser_manual", description="Origin of playback context"),
    profile: str = Form(REAL_PROFILE_NAME, description="Classifier head: real or demo"),
):
    """
    Performs real-time two-pass detection and risk scoring on an uploaded audio clip.
    If duration is ~2.0s, performs Pass 1 (Primary).
    If duration is ~5.0s, performs Pass 2 (Verification).

    ``profile`` selects the classifier head. The demo head adds a
    ``firecracker`` class that is aliased to ``gunshot`` for risk scoring and
    escalation; responses always carry both ``candidate`` (the resolved class
    the rest of the system acts on) and ``raw_candidate`` (what the head
    actually predicted), so a demo detection is never mistaken for a real one.
    """
    active_detector, active_profile = _get_detector(profile)

    if not 0.30 <= sensitivity_threshold <= 0.70:
        raise HTTPException(status_code=422, detail="Sensitivity threshold must be between 0.30 and 0.70.")
    if primary_candidate is not None and primary_candidate not in active_profile.class_mapping:
        raise HTTPException(
            status_code=422,
            detail="Pass 2 candidate must be a class of the '{}' profile.".format(active_profile.name),
        )
    if primary_candidate is not None and primary_candidate != "normal" and \
            active_profile.resolve_class(primary_candidate) not in RISK_CONFIG["hazard_classes"]:
        raise HTTPException(status_code=422, detail="Pass 2 candidate must be a supported hazard class.")
    if primary_confidence is not None and not 0.0 <= primary_confidence <= 1.0:
        raise HTTPException(status_code=422, detail="Pass 1 confidence must be between 0 and 1.")
    if context_source not in {"browser_manual", "platform_signal"}:
        raise HTTPException(status_code=422, detail="Invalid context source.")

    temp_path = None
    try:
        # Read uploaded file bytes
        file_bytes = await file.read()

        # Save temp file to read with soundfile
        os.makedirs("temp", exist_ok=True)
        # uuid4, not time.time(): concurrent requests can land in the same
        # fractional second and silently clobber each other's temp file.
        temp_path = "temp/{}_chunk.wav".format(uuid.uuid4().hex)
        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        import soundfile as sf
        audio_data, sr = sf.read(temp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to process uploaded audio: {}".format(e))
    finally:
        # Prevent temporary file leaks by ensuring cleanup on failure
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    profile_meta = {
        "profile": active_profile.name,
        "profile_banner": active_profile.banner,
    }

    try:
        if duration <= 3.0:
            # Run Pass 1
            has_candidate, candidate, confidence, acoustic_media_score = active_detector.run_pass_1(
                audio_data, sr, sensitivity_threshold
            )
            resolved = active_detector.resolve_class(candidate)
            effective_media_playback, effective_context_source = _resolve_media_context(
                media_playback, context_source, acoustic_media_score
            )

            # Immediate verification for transient events (gunshot, explosion, glass_breaking)
            if has_candidate and resolved in ["gunshot", "explosion", "glass_breaking"]:
                risk_score, risk_level = scorer.calculate_risk(
                    primary_conf=confidence,
                    verification_conf=confidence,
                    media_playback=effective_media_playback,
                    sudden_motion=sudden_motion,
                    current_class=resolved,
                    context_id=user_id
                )
                repeats = scorer.get_repeated_impulse_count(user_id)
                decision = decide_action(
                    verified=True, class_name=resolved, risk_score=risk_score,
                    media_playback=effective_media_playback, sudden_motion=sudden_motion,
                    repeat_count=repeats, context_source=effective_context_source,
                )
                return {
                    "pass": 1,
                    "has_candidate": True,
                    "candidate": resolved,
                    "raw_candidate": candidate,
                    "alias_applied": resolved != candidate,
                    "confidence": confidence,
                    "immediate_verification": True,
                    "verified": True,
                    "primary_confidence": confidence,
                    "verification_confidence": confidence,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "should_alert": decision.should_notify,
                    "media_suppressed": decision.state == "LIKELY_PLAYBACK_REVIEW",
                    "acoustic_media_score": acoustic_media_score,
                    "acoustic_media_detected": effective_context_source == "acoustic_signal",
                    "decision": decision.to_dict(),
                    **profile_meta,
                }

            return {
                "pass": 1,
                "has_candidate": has_candidate,
                "candidate": resolved,
                "raw_candidate": candidate,
                "alias_applied": resolved != candidate,
                "confidence": confidence,
                "immediate_verification": False,
                "acoustic_media_score": acoustic_media_score,
                **profile_meta,
            }
        else:
            # Run Pass 2 (Requires candidate parameter to be verified).
            # Pass 1 always looks at a real 2-second window; slicing a fixed 2/5 fraction
            # silently shrank the window for clips that were not exactly 5s long.
            # A live second pass must verify the candidate produced by the preceding
            # two-second recording, not silently re-classify unrelated audio.
            if primary_candidate is not None and primary_confidence is not None:
                has_candidate = primary_candidate != "normal"
                candidate = primary_candidate
                p1_conf = primary_confidence
                p1_acoustic_media_score = 0.0
            else:
                pass_1_samples = min(len(audio_data), int(2.0 * sr))
                has_candidate, candidate, p1_conf, p1_acoustic_media_score = active_detector.run_pass_1(
                    audio_data[:pass_1_samples], sr, sensitivity_threshold
                )

            if not has_candidate:
                effective_media_playback, effective_context_source = _resolve_media_context(
                    media_playback, context_source, p1_acoustic_media_score
                )
                return {
                    "pass": 2,
                    "verified": False,
                    "candidate": "normal",
                    "raw_candidate": "normal",
                    "alias_applied": False,
                    "confidence": p1_conf,
                    "primary_confidence": p1_conf,
                    "verification_confidence": 0.0,
                    "risk_score": 0,
                    "risk_level": "NORMAL",
                    "acoustic_media_score": p1_acoustic_media_score,
                    "acoustic_media_detected": effective_context_source == "acoustic_signal",
                    "decision": decide_action(
                        verified=False, class_name="normal", risk_score=0,
                        media_playback=effective_media_playback, sudden_motion=sudden_motion,
                        repeat_count=0, context_source=effective_context_source,
                    ).to_dict(),
                    **profile_meta,
                }

            verified, p2_conf, p2_acoustic_media_score = active_detector.run_pass_2(
                audio_data, sr, candidate
            )
            resolved = active_detector.resolve_class(candidate)
            acoustic_media_score = max(p1_acoustic_media_score, p2_acoustic_media_score)
            effective_media_playback, effective_context_source = _resolve_media_context(
                media_playback, context_source, acoustic_media_score
            )

            # Calculate Risk Score
            risk_score, risk_level = scorer.calculate_risk(
                primary_conf=p1_conf,
                verification_conf=p2_conf if verified else 0.0,
                media_playback=effective_media_playback,
                sudden_motion=sudden_motion,
                current_class=resolved if verified else "normal",
                context_id=user_id
            )

            repeats = scorer.get_repeated_impulse_count(user_id)
            decision = decide_action(
                verified=verified, class_name=resolved, risk_score=risk_score,
                media_playback=effective_media_playback, sudden_motion=sudden_motion,
                repeat_count=repeats, context_source=effective_context_source,
            )
            return {
                "pass": 2,
                "verified": verified,
                "candidate": resolved,
                "raw_candidate": candidate,
                "alias_applied": resolved != candidate,
                "primary_confidence": p1_conf,
                "verification_confidence": p2_conf,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "should_alert": decision.should_notify,
                "media_suppressed": decision.state == "LIKELY_PLAYBACK_REVIEW",
                "acoustic_media_score": acoustic_media_score,
                "acoustic_media_detected": effective_context_source == "acoustic_signal",
                "decision": decision.to_dict(),
                **profile_meta,
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Inference error: {}".format(e))


@app.post("/events", response_model=EventResponse)
def log_event(event: EventCreate):
    with get_db() as conn:
        cursor = conn.cursor()
        timestamp = time.time()
        cursor.execute(
            "INSERT INTO events (user_id, timestamp, class_name, primary_conf, verification_conf, risk_score, risk_level) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event.user_id, timestamp, event.class_name, event.primary_conf, event.verification_conf, event.risk_score, event.risk_level)
        )
        event_id = cursor.lastrowid
        conn.commit()

    return {
        "id": event_id,
        "user_id": event.user_id,
        "timestamp": timestamp,
        "class_name": event.class_name,
        "primary_conf": event.primary_conf,
        "verification_conf": event.verification_conf,
        "risk_score": event.risk_score,
        "risk_level": event.risk_level
    }

@app.get("/events/{user_id}", response_model=List[EventResponse])
def get_event_history(user_id: str):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
        rows = cursor.fetchall()

    return [dict(row) for row in rows]

@app.get("/readiness")
def get_readiness():
    """Report whether locally available data supports a real-world deployment claim."""
    return assess_dataset_readiness(DATA_PATH)

@app.delete("/events/{user_id}")
def clear_event_history(user_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
        conn.commit()
    return {"status": "success"}

@app.post("/contacts", response_model=ContactResponse)
def add_contact(contact: ContactCreate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (user_id, name, phone, relation, telegram_chat_id, "
            "priority, notify_call, notify_telegram) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                contact.user_id, contact.name, contact.phone, contact.relation,
                contact.telegram_chat_id,
                100 if contact.priority is None else contact.priority,
                1 if contact.notify_call is None else int(contact.notify_call),
                1 if contact.notify_telegram is None else int(contact.notify_telegram),
            )
        )
        contact_id = cursor.lastrowid
        conn.commit()

    return {
        "id": contact_id,
        "user_id": contact.user_id,
        "name": contact.name,
        "phone": contact.phone,
        "relation": contact.relation,
        "telegram_chat_id": contact.telegram_chat_id,
        "priority": 100 if contact.priority is None else contact.priority,
        "notify_call": True if contact.notify_call is None else contact.notify_call,
        "notify_telegram": True if contact.notify_telegram is None else contact.notify_telegram,
    }

@app.get("/contacts/{user_id}", response_model=List[ContactResponse])
def get_contacts(user_id: str):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY COALESCE(priority, 100), id",
            (user_id,),
        )
        rows = cursor.fetchall()

    contacts = []
    for row in rows:
        item = dict(row)
        item["notify_call"] = bool(item.get("notify_call", 1))
        item["notify_telegram"] = bool(item.get("notify_telegram", 1))
        contacts.append(item)
    return contacts

@app.patch("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(contact_id: int, update: ContactUpdate, user_id: str = Query(...)):
    """Edits escalation routing on an existing contact (Telegram chat id,
    priority, per-channel opt-outs) without forcing a delete-and-re-add."""
    fields = {}
    for key, value in update.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        fields[key] = int(value) if key in {"notify_call", "notify_telegram"} else value
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update.")

    assignments = ", ".join("{} = ?".format(key) for key in fields)
    params = list(fields.values()) + [contact_id, user_id]
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE contacts SET {} WHERE id = ? AND user_id = ?".format(assignments), params
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Contact not found.")
        conn.commit()
        cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        row = dict(cursor.fetchone())

    row["notify_call"] = bool(row.get("notify_call", 1))
    row["notify_telegram"] = bool(row.get("notify_telegram", 1))
    return row

@app.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, user_id: str = Query(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Contact not found.")
        conn.commit()

    return {"status": "success", "message": "Contact {} deleted".format(contact_id)}

@app.get("/nearby")
def get_nearby_places(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    place_type: str = Query(..., alias="type", description="Type of service: hospital, police, fire")
):
    osm_node_type = "amenity"
    osm_val = ""
    if place_type == "hospital":
        osm_val = "hospital"
    elif place_type == "police":
        osm_val = "police"
    elif place_type == "fire":
        osm_val = "fire_station"
    else:
        raise HTTPException(status_code=400, detail="Invalid place type.")

    overpass_query = """
    [out:json];
    node["{}"="{}"](around:5000, {}, {});
    out body;
    """.format(osm_node_type, osm_val, lat, lng)
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Overpass rejects the default requests User-Agent with HTTP 406, and returns 504 when
    # its slots are busy, so identify the client and retry a couple of times before falling back.
    headers = {"User-Agent": "EchoSafetyApp/1.0 (emergency sound detection nearby amenities)"}
    try:
        response = None
        for attempt in range(3):
            response = requests.post(overpass_url, data={"data": overpass_query}, headers=headers, timeout=30)
            if response.status_code == 200:
                break
        response.raise_for_status()
        data = response.json()
        places = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            places.append({
                "name": tags.get("name", "Unnamed {}".format(place_type.capitalize())),
                "latitude": element.get("lat"),
                "longitude": element.get("lon"),
                "address": tags.get("addr:street", "Street address unavailable")
            })
        return {"status": "success", "results": places[:10]}
    except Exception:
        return {
            "status": "fallback",
            "simulated": True,
            "message": "OSM Overpass API failure. Using local mock coordinates.",
            "results": [
                {
                    "name": "City Emergency {}".format(place_type.capitalize()),
                    "latitude": lat + 0.005,
                    "longitude": lng - 0.003,
                    "address": "123 Civic Center Way"
                },
                {
                    "name": "Central District {}".format(place_type.capitalize()),
                    "latitude": lat - 0.002,
                    "longitude": lng + 0.006,
                    "address": "456 Safety Blvd"
                }
            ]
        }

@app.post("/demo/nearby-corroboration")
def get_demo_corroboration(lat: float, lng: float, class_name: str):
    return {
        "simulated": True,
        "active_danger_zone": True if class_name in ["gunshot", "explosion"] else False,
        "corroborated_reports_count": 3,
        "time_window_minutes": 5,
        "alert_corroborated": True
    }

# Mount Data static directory
data_dir_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model", "data"))
os.makedirs(data_dir_path, exist_ok=True)
app.mount("/data", StaticFiles(directory=data_dir_path), name="data")

# Mount Web Emulator static assets. This is a catch-all mount and must stay
# last: anything registered after it becomes unreachable.
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
