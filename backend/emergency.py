"""Incident lifecycle and contact escalation.

Why this exists
---------------
Until now Echo only ever showed an alert to the person who was already in the
room -- which is the one person who does not need to be told. This module
turns a verified high-risk detection into an *outbound* escalation to the
people the user nominated: an automated voice call that plays the five
seconds of audio Echo actually heard, and a Telegram message carrying the same
clip, the class, the risk score, and the location.

Safety rules encoded here (not optional, not configurable away)
--------------------------------------------------------------
1. **Cancel window.** An incident is created in ``PENDING`` and only dispatches
   after ``settings.cancel_window_seconds``. The person in the room can cancel
   it from the app in one tap. A model score is evidence, not proof.
2. **Risk floor.** Auto-escalation requires ``risk_score >= settings.min_risk_score``
   and a verified detection. Anything below that is logged, not broadcast.
3. **Cooldown.** One escalation per user per ``settings.cooldown_seconds``.
   A firecracker night must not dial a contact forty times.
4. **No emergency-services auto-dial.** This escalates to the user's *own*
   nominated contacts only. Calling 112/police stays user-initiated, exactly as
   docs/SAFETY_IMPLEMENTATION_PLAN.md requires -- a personal contact can judge
   a false alarm and hang up; a dispatched police unit cannot be un-dispatched.
5. **Honest wording.** Every message says "may be in danger" and "what sounded
   like", and demo-profile incidents announce themselves as demonstrations.
6. **Per-channel truth.** Each attempt records sent / simulated / failed with a
   detail string, and the app shows exactly that. No silent failures.
"""

import os
import sqlite3
import time
import uuid

from config import settings
from db import EVIDENCE_DIR, get_db
from geocode import reverse_geocode
from notifiers import (
    TelegramNotifier,
    VoiceCaller,
    build_telegram_message,
    build_voice_script,
)

# place_label values the app/browser send as a placeholder rather than a
# real address (see backend/static/app.js and api_service.dart). Any of
# these gets replaced by a resolved address when one is available -- a
# contact reading "Last known location" in a real alert learns nothing an
# actual street name would have told them.
_GENERIC_PLACE_LABELS = {None, "", "Last known location", "Location"}

STATE_PENDING = "PENDING"
STATE_CANCELLED = "CANCELLED"
STATE_DISPATCHING = "DISPATCHING"
STATE_DISPATCHED = "DISPATCHED"
STATE_NO_CONTACTS = "NO_CONTACTS"
STATE_SUPPRESSED = "SUPPRESSED"

# Classes that may trigger an outbound escalation at all. A siren (someone
# else's emergency driving past) or a distant shout is not grounds for calling
# a contact and reading them an alarm script.
ESCALATION_CLASSES = {"gunshot", "explosion", "scream", "glass_breaking", "fire_alarm"}


def _row_to_dict(row):
    return dict(row) if row is not None else None


def evidence_path(incident_id):
    return os.path.join(EVIDENCE_DIR, "{}.wav".format(incident_id))


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------

def escalation_gate(*, verified, class_name, risk_score, user_id, force=False):
    """Decides whether this detection may escalate to contacts.

    Returns (allowed, reason). ``force=True`` is the user's own "escalate now"
    button, which skips the class/risk gate but never skips the cooldown check
    silently -- it reports it.
    """
    if not settings.escalation_enabled:
        return False, "Outbound escalation is disabled on this backend (ECHO_ESCALATION_ENABLED=0)."
    if not force:
        if not verified:
            return False, "Detection was not verified by pass 2."
        if class_name not in ESCALATION_CLASSES:
            return False, "Class '{}' is not an escalation class.".format(class_name)
        if risk_score < settings.min_risk_score:
            return False, "Risk score {} is below the escalation floor of {}.".format(
                risk_score, int(settings.min_risk_score)
            )

    last = last_escalation_time(user_id)
    if last is not None and (time.time() - last) < settings.cooldown_seconds:
        remaining = settings.cooldown_seconds - (time.time() - last)
        return False, "Cooldown active; {:.0f}s until contacts can be alerted again.".format(
            remaining
        )
    return True, "Eligible for contact escalation."


def last_escalation_time(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT MAX(dispatched_at) FROM incidents WHERE user_id = ? AND dispatched_at IS NOT NULL",
            (user_id,),
        )
        row = cursor.fetchone()
    return row[0] if row and row[0] else None


# --------------------------------------------------------------------------
# Incident CRUD
# --------------------------------------------------------------------------

def create_incident(*, user_id, class_name, raw_class=None, profile="real",
                    primary_conf=0.0, verification_conf=0.0, risk_score=0,
                    risk_level="NORMAL", latitude=None, longitude=None,
                    accuracy_m=None, place_label=None, clip_bytes=None,
                    clip_seconds=None, state=STATE_PENDING, note=None,
                    cancel_window=None):
    incident_id = uuid.uuid4().hex
    created_at = time.time()
    window = settings.cancel_window_seconds if cancel_window is None else cancel_window
    cancel_deadline = created_at + window if state == STATE_PENDING else None

    clip_path = None
    if clip_bytes:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        clip_path = evidence_path(incident_id)
        with open(clip_path, "wb") as clip_file:
            clip_file.write(clip_bytes)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO incidents (
                id, user_id, created_at, class_name, raw_class, profile,
                primary_conf, verification_conf, risk_score, risk_level,
                latitude, longitude, accuracy_m, place_label, clip_path,
                clip_seconds, state, cancel_deadline, note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                incident_id, user_id, created_at, class_name, raw_class, profile,
                primary_conf, verification_conf, int(risk_score), risk_level,
                latitude, longitude, accuracy_m, place_label, clip_path,
                clip_seconds, state, cancel_deadline, note,
            ),
        )
        conn.commit()

    purge_expired_clips()
    return get_incident(incident_id)


def get_incident(incident_id, include_attempts=True):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        incident = _row_to_dict(cursor.fetchone())
        if incident is None:
            return None
        if include_attempts:
            cursor.execute(
                "SELECT * FROM escalation_attempts WHERE incident_id = ? ORDER BY id",
                (incident_id,),
            )
            incident["attempts"] = [dict(row) for row in cursor.fetchall()]
    incident["seconds_to_dispatch"] = (
        max(0.0, incident["cancel_deadline"] - time.time())
        if incident.get("cancel_deadline") and incident["state"] == STATE_PENDING
        else 0.0
    )
    incident["has_clip"] = bool(incident.get("clip_path")) and os.path.exists(
        incident.get("clip_path") or ""
    )
    return incident


def list_incidents(user_id, limit=50):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM incidents WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        incidents = [dict(row) for row in cursor.fetchall()]
        for incident in incidents:
            cursor.execute(
                "SELECT * FROM escalation_attempts WHERE incident_id = ? ORDER BY id",
                (incident["id"],),
            )
            incident["attempts"] = [dict(row) for row in cursor.fetchall()]
            incident["has_clip"] = bool(incident.get("clip_path")) and os.path.exists(
                incident.get("clip_path") or ""
            )
    return incidents


def cancel_incident(incident_id, user_id=None, note="Cancelled by the user."):
    """Marks an incident cancelled. Only a PENDING incident can be cancelled --
    once contacts have been called, pretending it did not happen would be a lie
    to both the user and the contacts who already picked up."""
    with get_db() as conn:
        cursor = conn.cursor()
        params = [note, time.time(), incident_id]
        query = (
            "UPDATE incidents SET state = 'CANCELLED', note = ?, cancelled_at = ? "
            "WHERE id = ? AND state = 'PENDING'"
        )
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        cursor.execute(query, params)
        changed = cursor.rowcount
        conn.commit()
    return changed > 0


def _set_state(incident_id, state, **fields):
    assignments = ["state = ?"]
    params = [state]
    for key, value in fields.items():
        assignments.append("{} = ?".format(key))
        params.append(value)
    params.append(incident_id)
    with get_db() as conn:
        conn.execute(
            "UPDATE incidents SET {} WHERE id = ?".format(", ".join(assignments)), params
        )
        conn.commit()


def _record_attempt(incident_id, contact_id, contact_name, channel, status, detail):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO escalation_attempts (incident_id, contact_id, contact_name, "
            "channel, status, detail, created_at) VALUES (?,?,?,?,?,?,?)",
            (incident_id, contact_id, contact_name, channel, status, detail, time.time()),
        )
        conn.commit()


def escalation_contacts(user_id):
    """Contacts in escalation order (lowest priority number first, then id)."""
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY COALESCE(priority, 100), id",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

def dispatch_incident(incident_id, telegram=None, voice=None, user_label=None):
    """Runs the outbound escalation. Blocking; call it off the event loop.

    Returns the updated incident dict. Safe to call twice: the PENDING ->
    DISPATCHING transition is guarded, so a duplicate call is a no-op instead
    of a second round of phone calls.
    """
    incident = get_incident(incident_id)
    if incident is None:
        return None
    if incident["state"] != STATE_PENDING:
        return incident

    # Claim the incident before doing any network work.
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE incidents SET state = ? WHERE id = ? AND state = ?",
            (STATE_DISPATCHING, incident_id, STATE_PENDING),
        )
        claimed = cursor.rowcount
        conn.commit()
    if not claimed:
        return get_incident(incident_id)

    telegram = telegram or TelegramNotifier()
    voice = voice or VoiceCaller()
    label = user_label or incident["user_id"]

    contacts = escalation_contacts(incident["user_id"])
    if not contacts:
        _record_attempt(
            incident_id, None, None, "none", "failed",
            "No emergency contacts are saved for this user, so nobody could be alerted.",
        )
        _set_state(incident_id, STATE_NO_CONTACTS, note="No emergency contacts configured.")
        return get_incident(incident_id)

    # Resolve a real address for the coordinates, lazily -- only for
    # incidents that actually reach dispatch, so a cancelled-in-time alert
    # never spends a lookup. Best-effort: reverse_geocode() never raises, and
    # the exact lat/lng + Maps link are sent regardless of whether this
    # succeeds, so a geocoding outage degrades the message, it never breaks
    # dispatch.
    if incident.get("place_label") in _GENERIC_PLACE_LABELS:
        resolved_label = reverse_geocode(incident.get("latitude"), incident.get("longitude"))
        if resolved_label:
            incident["place_label"] = resolved_label
            with get_db() as conn:
                conn.execute(
                    "UPDATE incidents SET place_label = ? WHERE id = ?",
                    (resolved_label, incident_id),
                )
                conn.commit()

    message = build_telegram_message(incident, label)
    script = build_voice_script(incident, label)
    clip_path = incident.get("clip_path")

    for contact in contacts:
        contact_id = contact.get("id")
        contact_name = contact.get("name")

        if contact.get("notify_telegram", 1):
            status, detail = telegram.send_alert(
                chat_id=contact.get("telegram_chat_id"),
                message=message,
                clip_path=clip_path,
                latitude=incident.get("latitude"),
                longitude=incident.get("longitude"),
            )
            _record_attempt(incident_id, contact_id, contact_name, "telegram", status, detail)

        if contact.get("notify_call", 1):
            status, detail = voice.place_call(
                to_number=contact.get("phone"),
                incident_id=incident_id,
                script=script,
            )
            _record_attempt(incident_id, contact_id, contact_name, "voice_call", status, detail)

    _set_state(incident_id, STATE_DISPATCHED, dispatched_at=time.time())
    return get_incident(incident_id)


def due_pending_incidents(now=None):
    """PENDING incidents whose cancel window has elapsed.

    A restart in the middle of a cancel window must not strand an incident:
    the app polls, and the backend also sweeps this list on a timer.
    """
    now = now or time.time()
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM incidents WHERE state = ? AND cancel_deadline IS NOT NULL "
            "AND cancel_deadline <= ?",
            (STATE_PENDING, now),
        )
        return [row["id"] for row in cursor.fetchall()]


def purge_expired_clips(now=None):
    """Deletes evidence clips past the retention window.

    Recorded audio of someone's home is the most sensitive thing this system
    holds; keeping it forever by default would be indefensible.
    """
    now = now or time.time()
    cutoff = now - settings.clip_retention_seconds
    removed = 0
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, clip_path FROM incidents WHERE clip_path IS NOT NULL AND created_at < ?",
            (cutoff,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            path = row["clip_path"]
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    continue
            conn.execute("UPDATE incidents SET clip_path = NULL WHERE id = ?", (row["id"],))
        conn.commit()
    return removed
