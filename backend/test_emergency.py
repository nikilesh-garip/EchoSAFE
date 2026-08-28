"""Tests for the emergency-escalation layer.

These deliberately import nothing from main.py so they run without
TensorFlow: the escalation path is the part that has to be correct when
somebody is actually in trouble, and it should be testable in a second.
"""

import os
import tempfile

os.environ["ECHO_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="echo_test_db_"), "test.db")
os.environ.setdefault("ECHO_ESCALATION_ENABLED", "1")

import emergency  # noqa: E402
from config import settings  # noqa: E402
from db import get_db, init_db  # noqa: E402
from notifiers import (  # noqa: E402
    build_telegram_message,
    build_twiml,
    build_voice_script,
)

init_db()

settings.cancel_window_seconds = 0.0
settings.cooldown_seconds = 0.0
settings.min_risk_score = 61


class FakeTelegram:
    def __init__(self, status="sent"):
        self.status = status
        self.calls = []

    def send_alert(self, chat_id, message, clip_path=None, latitude=None, longitude=None):
        self.calls.append({
            "chat_id": chat_id, "message": message, "clip_path": clip_path,
            "latitude": latitude, "longitude": longitude,
        })
        return self.status, "fake telegram"


class FakeVoice:
    def __init__(self, status="sent"):
        self.status = status
        self.calls = []

    def place_call(self, to_number, incident_id, script):
        self.calls.append({"to": to_number, "incident": incident_id, "script": script})
        return self.status, "fake call"


def _add_contact(user_id, name="Amma", phone="+919000000000", chat_id="12345",
                 priority=1, notify_call=1, notify_telegram=1):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (user_id, name, phone, relation, telegram_chat_id, "
            "priority, notify_call, notify_telegram) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name, phone, "Parent", chat_id, priority, notify_call, notify_telegram),
        )
        conn.commit()
        return cursor.lastrowid


def test_gate_rejects_unverified_low_risk_and_non_escalation_classes():
    allowed, reason = emergency.escalation_gate(
        verified=False, class_name="gunshot", risk_score=90, user_id="gate_user_1")
    assert not allowed and "not verified" in reason

    allowed, reason = emergency.escalation_gate(
        verified=True, class_name="gunshot", risk_score=40, user_id="gate_user_2")
    assert not allowed and "below the escalation floor" in reason

    # A passing siren is somebody else's emergency; it must not call anyone.
    allowed, reason = emergency.escalation_gate(
        verified=True, class_name="siren", risk_score=95, user_id="gate_user_3")
    assert not allowed and "not an escalation class" in reason

    allowed, _ = emergency.escalation_gate(
        verified=True, class_name="gunshot", risk_score=85, user_id="gate_user_4")
    assert allowed


def test_cancelled_incident_never_dispatches():
    user = "cancel_user"
    _add_contact(user)
    incident = emergency.create_incident(
        user_id=user, class_name="gunshot", risk_score=88, risk_level="HIGH_RISK",
        primary_conf=0.9, verification_conf=0.9, cancel_window=60,
    )
    assert incident["state"] == emergency.STATE_PENDING
    assert emergency.cancel_incident(incident["id"], user_id=user)

    telegram, voice = FakeTelegram(), FakeVoice()
    result = emergency.dispatch_incident(incident["id"], telegram=telegram, voice=voice)
    assert result["state"] == emergency.STATE_CANCELLED
    assert telegram.calls == [] and voice.calls == []


def test_dispatch_alerts_every_channel_and_records_status():
    user = "dispatch_user"
    _add_contact(user, name="Amma", chat_id="111", priority=1)
    _add_contact(user, name="Roommate", phone="+919111111111", chat_id="222", priority=2)

    incident = emergency.create_incident(
        user_id=user, class_name="gunshot", raw_class="firecracker", profile="demo",
        risk_score=92, risk_level="HIGH_RISK", primary_conf=0.94, verification_conf=0.91,
        latitude=17.385, longitude=78.4867, clip_bytes=b"RIFFfake", clip_seconds=5.0,
        cancel_window=0,
    )
    telegram, voice = FakeTelegram(), FakeVoice()
    result = emergency.dispatch_incident(
        incident["id"], telegram=telegram, voice=voice, user_label="Mahendhar")

    assert result["state"] == emergency.STATE_DISPATCHED
    assert len(telegram.calls) == 2 and len(voice.calls) == 2
    # Priority ordering: the first contact listed is contacted first.
    assert telegram.calls[0]["chat_id"] == "111"
    assert [a["status"] for a in result["attempts"]] == ["sent"] * 4
    assert result["attempts"][0]["channel"] == "telegram"

    # The clip really was written to disk and handed to the notifier.
    assert os.path.exists(result["clip_path"])
    assert telegram.calls[0]["clip_path"] == result["clip_path"]

    # A second dispatch of the same incident must not re-alert anyone.
    emergency.dispatch_incident(incident["id"], telegram=telegram, voice=voice)
    assert len(voice.calls) == 2


def test_dispatch_without_contacts_is_reported_not_silent():
    incident = emergency.create_incident(
        user_id="lonely_user", class_name="gunshot", risk_score=90,
        risk_level="HIGH_RISK", cancel_window=0,
    )
    result = emergency.dispatch_incident(
        incident["id"], telegram=FakeTelegram(), voice=FakeVoice())
    assert result["state"] == emergency.STATE_NO_CONTACTS
    assert result["attempts"][0]["status"] == "failed"
    assert "No emergency contacts" in result["attempts"][0]["detail"]


def test_per_channel_opt_out_is_honoured():
    user = "optout_user"
    _add_contact(user, name="TelegramOnly", notify_call=0, notify_telegram=1)
    incident = emergency.create_incident(
        user_id=user, class_name="explosion", risk_score=90,
        risk_level="HIGH_RISK", cancel_window=0,
    )
    telegram, voice = FakeTelegram(), FakeVoice()
    emergency.dispatch_incident(incident["id"], telegram=telegram, voice=voice)
    assert len(telegram.calls) == 1
    assert voice.calls == []


def test_cooldown_blocks_a_second_escalation():
    user = "cooldown_user"
    _add_contact(user)
    settings.cooldown_seconds = 300.0
    try:
        incident = emergency.create_incident(
            user_id=user, class_name="gunshot", risk_score=90,
            risk_level="HIGH_RISK", cancel_window=0,
        )
        emergency.dispatch_incident(incident["id"], telegram=FakeTelegram(), voice=FakeVoice())
        allowed, reason = emergency.escalation_gate(
            verified=True, class_name="gunshot", risk_score=95, user_id=user)
        assert not allowed and "Cooldown" in reason
    finally:
        settings.cooldown_seconds = 0.0


def test_messages_are_hedged_and_carry_evidence():
    incident = {
        "class_name": "gunshot", "raw_class": "firecracker", "profile": "demo",
        "risk_score": 88, "risk_level": "HIGH_RISK", "primary_conf": 0.9,
        "verification_conf": 0.87, "latitude": 17.385044, "longitude": 78.486671,
        "place_label": "Last known location",
    }
    message = build_telegram_message(incident, "Mahendhar")
    assert "may be in danger" in message
    assert "what sounded like a gunshot" in message
    assert "maps.google.com/?q=17.385044,78.486671" in message
    assert "raw acoustic class: firecracker" in message.lower()
    assert "DEMO ALERT" in message

    script = build_voice_script(incident, "Mahendhar")
    assert script.startswith("This is a demonstration alert")
    assert "risk score of 88 out of 100" in script

    twiml = build_twiml(script, "https://example.test/incidents/abc/clip")
    assert twiml.count("<Say") == 3  # script twice, then the sign-off
    assert twiml.count("<Play>") == 2
    assert "<Response>" in twiml and "</Response>" in twiml


def test_message_states_location_is_missing_rather_than_faking_one():
    message = build_telegram_message(
        {"class_name": "scream", "risk_score": 70, "risk_level": "POSSIBLE_DANGER",
         "primary_conf": 0.8, "verification_conf": 0.8}, "Someone")
    assert "Location: unavailable" in message


def test_clip_retention_purge_removes_expired_audio():
    incident = emergency.create_incident(
        user_id="retention_user", class_name="gunshot", risk_score=90,
        risk_level="HIGH_RISK", clip_bytes=b"RIFFfake", cancel_window=0,
    )
    path = incident["clip_path"]
    assert os.path.exists(path)
    # Pretend the clip is older than the retention window.
    with get_db() as conn:
        conn.execute("UPDATE incidents SET created_at = 0 WHERE id = ?", (incident["id"],))
        conn.commit()
    emergency.purge_expired_clips()
    assert not os.path.exists(path)
    assert emergency.get_incident(incident["id"])["clip_path"] is None


def test_dispatch_resolves_a_real_address_for_a_placeholder_label(monkeypatch):
    """A generic client-sent place_label ('Last known location') must be
    replaced by a real resolved address at dispatch time, and persisted onto
    the incident so later reads (history, the app's alert screen) see it
    too -- not just the one Telegram message that happened to go out."""
    calls = {"count": 0}

    def fake_geocode(latitude, longitude, timeout=6.0):
        calls["count"] += 1
        return "Road 12, Banjara Hills, Hyderabad"

    monkeypatch.setattr(emergency, "reverse_geocode", fake_geocode)

    user = "geocode_user"
    _add_contact(user)
    incident = emergency.create_incident(
        user_id=user, class_name="gunshot", risk_score=90, risk_level="HIGH_RISK",
        latitude=17.385044, longitude=78.486671, place_label="Last known location",
        cancel_window=0,
    )
    telegram, voice = FakeTelegram(), FakeVoice()
    result = emergency.dispatch_incident(incident["id"], telegram=telegram, voice=voice)

    assert calls["count"] == 1
    assert result["place_label"] == "Road 12, Banjara Hills, Hyderabad"
    assert "Road 12, Banjara Hills, Hyderabad" in telegram.calls[0]["message"]
    # Persisted, not just returned in-memory.
    assert emergency.get_incident(incident["id"])["place_label"] == "Road 12, Banjara Hills, Hyderabad"


def test_dispatch_leaves_a_real_place_label_alone(monkeypatch):
    """If the client already sent a real place name, dispatch must not spend
    a geocoding lookup overwriting it."""
    def _fail_if_called(*a, **k):
        raise AssertionError("reverse_geocode should not be called for a non-placeholder label")

    monkeypatch.setattr(emergency, "reverse_geocode", _fail_if_called)

    user = "geocode_user_2"
    _add_contact(user)
    incident = emergency.create_incident(
        user_id=user, class_name="gunshot", risk_score=90, risk_level="HIGH_RISK",
        latitude=17.385044, longitude=78.486671, place_label="Home",
        cancel_window=0,
    )
    result = emergency.dispatch_incident(incident["id"], telegram=FakeTelegram(), voice=FakeVoice())
    assert result["place_label"] == "Home"


def test_due_pending_incidents_survives_a_restart():
    incident = emergency.create_incident(
        user_id="restart_user", class_name="gunshot", risk_score=90,
        risk_level="HIGH_RISK", cancel_window=0,
    )
    assert incident["id"] in emergency.due_pending_incidents()
    emergency.cancel_incident(incident["id"])
    assert incident["id"] not in emergency.due_pending_incidents()
