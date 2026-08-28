"""HTTP surface for the emergency-escalation layer.

Route map
---------
POST   /incidents                    create an incident (multipart, 5s clip)
GET    /incidents/user/{user_id}     incident history with per-channel results
GET    /incidents/{incident_id}      live state (used for the cancel countdown)
POST   /incidents/{incident_id}/cancel     "I'm safe" -- stops the escalation
POST   /incidents/{incident_id}/dispatch   "Alert them now" -- skips the countdown
GET    /incidents/{incident_id}/clip       the 5s evidence clip (Twilio + app)
GET    /incidents/{incident_id}/twiml      TwiML the automated call speaks
GET    /escalation/status            which channels are configured (no secrets)
POST   /escalation/test              send a clearly-labelled test to contacts
GET    /telegram/chats               chats that pressed Start on the bot
"""

import asyncio
import os
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

import emergency
from config import settings
from db import get_db
from notifiers import TelegramNotifier, VoiceCaller, build_twiml, build_voice_script

router = APIRouter()

# Cap on an uploaded evidence clip. 5 seconds of 16 kHz mono PCM is ~160 KB;
# 4 MB leaves generous headroom while refusing anything that is not a clip.
MAX_CLIP_BYTES = 4 * 1024 * 1024


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
# emergency.escalation_gate()'s cooldown only guards the /incidents path
# (a verified, risk-scored detection). /escalation/test intentionally skips
# that gate -- it is a rehearsal button -- which means without a limiter of
# its own it has NO cap on how often it can dial and message real contacts.
# A per-user in-memory sliding window is enough for a single-process
# deployment; it resets on restart, which is acceptable for what this
# protects (accidental double-taps and naive abuse, not a hardened API).
_rate_log = {}


def _rate_limited(bucket, key, limit, window_seconds):
    now = time.time()
    log_key = (bucket, key)
    stamps = [t for t in _rate_log.get(log_key, []) if now - t < window_seconds]
    stamps.append(now)
    _rate_log[log_key] = stamps
    return len(stamps) > limit


def _enforce_rate_limit(bucket, key, limit, window_seconds, message):
    if _rate_limited(bucket, key, limit, window_seconds):
        raise HTTPException(status_code=429, detail=message)


def _schedule_dispatch(incident_id, delay_seconds):
    """Dispatch after the cancel window, without blocking the event loop."""

    async def _runner():
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            await asyncio.to_thread(emergency.dispatch_incident, incident_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # a scheduler crash must not kill the server
            print("Escalation dispatch failed for {}: {}".format(incident_id, error))

    try:
        asyncio.get_running_loop().create_task(_runner())
    except RuntimeError:
        # No running loop (sync test client path): dispatch inline so the
        # behaviour is still observable rather than silently dropped.
        emergency.dispatch_incident(incident_id)


async def _sweep_loop(interval_seconds=5.0):
    """Backstop for incidents whose in-process timer was lost to a restart."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            for incident_id in await asyncio.to_thread(emergency.due_pending_incidents):
                await asyncio.to_thread(emergency.dispatch_incident, incident_id)
        except Exception as error:
            print("Escalation sweep error: {}".format(error))


def start_sweeper():
    try:
        asyncio.get_running_loop().create_task(_sweep_loop())
    except RuntimeError:
        pass


@router.get("/escalation/status")
def escalation_status():
    status = settings.public_status()
    status["escalation_classes"] = sorted(emergency.ESCALATION_CLASSES)
    return status


@router.post("/incidents")
async def create_incident(
    user_id: str = Form(...),
    class_name: str = Form(...),
    raw_class: Optional[str] = Form(None),
    profile: str = Form("real"),
    primary_conf: float = Form(0.0),
    verification_conf: float = Form(0.0),
    risk_score: int = Form(0),
    risk_level: str = Form("NORMAL"),
    verified: bool = Form(True),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    accuracy_m: Optional[float] = Form(None),
    place_label: Optional[str] = Form(None),
    user_label: Optional[str] = Form(None),
    force: bool = Form(False),
    clip: Optional[UploadFile] = File(None),
):
    """Creates an incident and arms the countdown to contact escalation.

    The response always includes ``escalation_armed`` and ``gate_reason`` so
    the app can say precisely why contacts will or will not be alerted --
    a silent no-op here would be the worst possible failure mode.
    """
    _enforce_rate_limit(
        "incidents", user_id, limit=20, window_seconds=60.0,
        message="Too many incidents created for this user in the last minute. Please slow down.",
    )

    clip_bytes = None
    if clip is not None:
        clip_bytes = await clip.read()
        if len(clip_bytes) > MAX_CLIP_BYTES:
            raise HTTPException(status_code=413, detail="Evidence clip is too large.")
        if not clip_bytes:
            clip_bytes = None

    allowed, reason = emergency.escalation_gate(
        verified=verified,
        class_name=class_name,
        risk_score=risk_score,
        user_id=user_id,
        force=force,
    )

    incident = emergency.create_incident(
        user_id=user_id,
        class_name=class_name,
        raw_class=raw_class,
        profile=profile,
        primary_conf=primary_conf,
        verification_conf=verification_conf,
        risk_score=risk_score,
        risk_level=risk_level,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        place_label=place_label,
        clip_bytes=clip_bytes,
        clip_seconds=settings.clip_seconds,
        state=emergency.STATE_PENDING if allowed else emergency.STATE_SUPPRESSED,
        note=None if allowed else reason,
    )

    if allowed:
        _schedule_dispatch(incident["id"], settings.cancel_window_seconds)

    incident["escalation_armed"] = allowed
    incident["gate_reason"] = reason
    incident["user_label"] = user_label or user_id
    return incident


@router.get("/incidents/user/{user_id}")
def incident_history(user_id: str, limit: int = 50):
    return emergency.list_incidents(user_id, limit=limit)


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str):
    incident = emergency.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@router.post("/incidents/{incident_id}/cancel")
def cancel_incident(incident_id: str, user_id: Optional[str] = Form(None),
                    note: str = Form("Marked safe by the user.")):
    incident = emergency.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    cancelled = emergency.cancel_incident(incident_id, user_id=user_id, note=note)
    if not cancelled:
        # Being explicit matters: the user must know whether contacts were
        # already called, not just that the button "did not work".
        return {
            "cancelled": False,
            "reason": "Incident is already in state '{}'; contacts may already have been "
                      "alerted.".format(incident["state"]),
            "incident": emergency.get_incident(incident_id),
        }
    return {"cancelled": True, "incident": emergency.get_incident(incident_id)}


@router.post("/incidents/{incident_id}/dispatch")
async def dispatch_now(incident_id: str, user_label: Optional[str] = Form(None)):
    incident = emergency.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if incident["state"] != emergency.STATE_PENDING:
        raise HTTPException(
            status_code=409,
            detail="Incident is in state '{}' and cannot be dispatched.".format(incident["state"]),
        )
    return await asyncio.to_thread(
        emergency.dispatch_incident, incident_id, None, None, user_label
    )


@router.get("/incidents/{incident_id}/clip")
def incident_clip(incident_id: str):
    incident = emergency.get_incident(incident_id, include_attempts=False)
    if incident is None or not incident.get("clip_path"):
        raise HTTPException(status_code=404, detail="No clip stored for this incident.")
    path = incident["clip_path"]
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Clip has been purged by the retention policy.")
    return FileResponse(path, media_type="audio/wav", filename="echo_{}.wav".format(incident_id))


@router.api_route("/incidents/{incident_id}/twiml", methods=["GET", "POST"])
def incident_twiml(incident_id: str):
    """Fetched by the telephony provider when the contact picks up."""
    incident = emergency.get_incident(incident_id, include_attempts=False)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    caller = VoiceCaller()
    clip_url = caller.clip_url(incident_id) if incident.get("has_clip") and caller.public_base_url else None
    script = build_voice_script(incident, incident.get("user_id"))
    return Response(content=build_twiml(script, clip_url), media_type="application/xml")


@router.get("/telegram/chats")
def telegram_chats():
    """Chats that have started the bot, so the app can bind a contact to one."""
    notifier = TelegramNotifier()
    return {
        "configured": notifier.configured,
        "hint": "Ask each contact to open your Echo bot in Telegram and press Start, "
                "then refresh this list and pick their chat.",
        "chats": notifier.recent_chats(),
    }


@router.post("/escalation/test")
async def escalation_test(user_id: str = Form(...), user_label: Optional[str] = Form(None)):
    """Sends a clearly-labelled rehearsal alert to every saved contact.

    Setup that is only ever exercised during a real emergency is setup that
    does not work. The message and the call both say "test" up front.
    """
    _enforce_rate_limit(
        "escalation_test", user_id, limit=1, window_seconds=60.0,
        message="A test alert was already sent in the last minute. Wait before sending another "
                "-- this endpoint calls and messages your real contacts.",
    )
    contacts = emergency.escalation_contacts(user_id)
    if not contacts:
        raise HTTPException(status_code=400, detail="No emergency contacts saved for this user.")

    incident = emergency.create_incident(
        user_id=user_id,
        class_name="normal",
        raw_class="test",
        profile="demo",
        primary_conf=0.0,
        verification_conf=0.0,
        risk_score=0,
        risk_level="TEST",
        state=emergency.STATE_PENDING,
        note="Escalation test initiated by the user.",
        cancel_window=0,
    )
    return await asyncio.to_thread(
        emergency.dispatch_incident, incident["id"], None, None,
        (user_label or user_id) + " (TEST -- no real emergency)",
    )


@router.get("/escalation/readiness/{user_id}")
def escalation_readiness(user_id: str):
    """Straight answer to: if something happened right now, who gets told?"""
    contacts = emergency.escalation_contacts(user_id)
    notifier = TelegramNotifier()
    caller = VoiceCaller()
    blockers = []
    if not contacts:
        blockers.append("No emergency contacts saved.")
    if not any(c.get("telegram_chat_id") for c in contacts):
        blockers.append("No contact has a Telegram chat id, so no clip or location can be sent.")
    if not any((c.get("phone") or "").strip() for c in contacts):
        blockers.append("No contact has a phone number, so nobody can be called.")
    if not notifier.configured:
        blockers.append("TELEGRAM_BOT_TOKEN is not set; Telegram alerts will be simulated only.")
    if not caller.configured:
        blockers.append(
            "Voice calling is not configured (needs TWILIO_* and ECHO_PUBLIC_BASE_URL); "
            "calls will be simulated only."
        )
    last = emergency.last_escalation_time(user_id)
    return {
        "user_id": user_id,
        "contact_count": len(contacts),
        "ready": not blockers,
        "blockers": blockers,
        "last_escalation_at": last,
        "cooldown_active": bool(last and (time.time() - last) < settings.cooldown_seconds),
        "channels": settings.public_status(),
    }


@router.get("/contacts-detail/{user_id}")
def contacts_detail(user_id: str):
    """Contacts including escalation routing columns (the legacy /contacts
    response is kept unchanged so older clients do not break)."""
    import sqlite3

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY COALESCE(priority, 100), id",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

