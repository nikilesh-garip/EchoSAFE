"""Outbound emergency channels: Telegram message + automated voice call.

Design notes
------------
* Both channels are **best-effort and independently reported**. A failed call
  must not stop the Telegram message, and vice versa -- an escalation that
  half-works still has to tell the user exactly which half worked.
* Neither channel is allowed to invent certainty. Every message says what the
  system *heard* and how confident it was; it never says "there is a shooting".
* When credentials are missing, both return ``status="simulated"`` with the
  full rendered payload, so the pipeline is demonstrable and testable offline.
* No SDK dependency: Twilio and Telegram are plain REST calls over `requests`,
  which the backend already depends on.
"""

import os
import xml.sax.saxutils as saxutils

import requests

from config import settings

# Human-readable phrasing for the classifier's class ids. Deliberately
# hedged ("what sounded like"): the model reports acoustic evidence.
CLASS_PHRASES = {
    "gunshot": "what sounded like a gunshot",
    "explosion": "what sounded like an explosion",
    "scream": "a scream",
    "glass_breaking": "glass breaking",
    "fire_alarm": "a fire alarm",
    "siren": "an emergency siren",
    "shouting": "someone shouting",
    "firecracker": "a firecracker burst",
    "normal": "an unusual sound",
}


def class_phrase(class_name):
    return CLASS_PHRASES.get(class_name, "a sound classified as " + str(class_name))


def maps_link(latitude, longitude):
    if latitude is None or longitude is None:
        return None
    return "https://maps.google.com/?q={:.6f},{:.6f}".format(latitude, longitude)


def build_voice_script(incident, user_label):
    """The words the automated call speaks before playing the evidence clip."""
    location_sentence = ""
    if incident.get("latitude") is not None and incident.get("longitude") is not None:
        location_sentence = " Their last known location has been sent to you on Telegram."
    demo_prefix = ""
    if incident.get("profile") == "demo":
        # A demo-profile call must announce itself. An automated emergency
        # call that sounds real but is a rehearsal is exactly the kind of
        # thing that must never be ambiguous to the person receiving it.
        demo_prefix = "This is a demonstration alert from the Echo safety system. "
    return (
        demo_prefix
        + "This is an automated safety alert from Echo. "
        + user_label + " may be in danger. "
        + "Echo detected " + class_phrase(incident["class_name"]) + " near them "
        + "with a risk score of " + str(int(incident.get("risk_score") or 0)) + " out of 100."
        + location_sentence
        + " Listen to the five seconds of audio that triggered this alert."
    )


def build_telegram_message(incident, user_label):
    lines = []
    if incident.get("profile") == "demo":
        lines.append("*DEMO ALERT (Echo demo profile - not a real emergency)*")
    else:
        lines.append("*ECHO EMERGENCY ALERT*")
    lines.append("")
    lines.append(user_label + " may be in danger.")
    lines.append("Echo detected " + class_phrase(incident["class_name"]) + ".")
    if incident.get("raw_class") and incident["raw_class"] != incident["class_name"]:
        lines.append("_Raw acoustic class: " + str(incident["raw_class"]) + "_")
    lines.append(
        "Risk score: {}/100 ({})".format(
            int(incident.get("risk_score") or 0), incident.get("risk_level") or "UNKNOWN"
        )
    )
    lines.append(
        "Confidence: pass 1 {:.0f}%, pass 2 {:.0f}%".format(
            float(incident.get("primary_conf") or 0) * 100,
            float(incident.get("verification_conf") or 0) * 100,
        )
    )
    link = maps_link(incident.get("latitude"), incident.get("longitude"))
    if link:
        label = incident.get("place_label")
        if label:
            lines.append("Exact location: " + str(label))
        lines.append(
            "Coordinates: {:.6f}, {:.6f}{}".format(
                incident["latitude"], incident["longitude"],
                " (Â±{:.0f}m)".format(incident["accuracy_m"])
                if incident.get("accuracy_m") else "",
            )
        )
        lines.append("Map: " + link)
    else:
        lines.append("Location: unavailable (no GPS fix on the device).")
    lines.append("")
    lines.append("The 5-second audio clip that triggered this alert is attached.")
    lines.append(
        "Echo classifies sound; it cannot confirm what happened. "
        "Please try to reach them directly."
    )
    return "\n".join(lines)


class TelegramNotifier:
    """Sends the alert text, the evidence clip, and a live location pin."""

    def __init__(self, token=None, api_base=None, timeout=None):
        self.token = token if token is not None else settings.telegram_bot_token
        self.api_base = (api_base or settings.telegram_api_base).rstrip("/")
        self.timeout = timeout or settings.request_timeout_seconds

    @property
    def configured(self):
        return bool(self.token)

    def _url(self, method):
        return "{}/bot{}/{}".format(self.api_base, self.token, method)

    def send_alert(self, chat_id, message, clip_path=None, latitude=None, longitude=None):
        """Returns (status, detail). status is sent | simulated | failed."""
        if not self.configured:
            return "simulated", (
                "TELEGRAM_BOT_TOKEN not set. Would have sent to chat "
                + str(chat_id) + ":\n" + message
            )
        if not chat_id:
            return "failed", "Contact has no Telegram chat id saved."

        try:
            response = requests.post(
                self._url("sendMessage"),
                data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                # Markdown parsing is the most common cause of a 400 here; a
                # failed alert because of an underscore in a contact name
                # would be an absurd way to lose an emergency message.
                response = requests.post(
                    self._url("sendMessage"),
                    data={"chat_id": chat_id, "text": message},
                    timeout=self.timeout,
                )
            if response.status_code != 200:
                return "failed", "sendMessage HTTP {}: {}".format(
                    response.status_code, response.text[:200]
                )

            details = ["message sent"]

            if clip_path and os.path.exists(clip_path):
                with open(clip_path, "rb") as clip:
                    audio_response = requests.post(
                        self._url("sendAudio"),
                        data={"chat_id": chat_id, "caption": "Audio that triggered the alert"},
                        files={"audio": (os.path.basename(clip_path), clip, "audio/wav")},
                        timeout=self.timeout,
                    )
                if audio_response.status_code != 200:
                    # Telegram rejects some WAV encodings for sendAudio but
                    # accepts anything as a document; the clip is evidence and
                    # must arrive one way or another.
                    with open(clip_path, "rb") as clip:
                        audio_response = requests.post(
                            self._url("sendDocument"),
                            data={"chat_id": chat_id, "caption": "Audio that triggered the alert"},
                            files={"document": (os.path.basename(clip_path), clip, "audio/wav")},
                            timeout=self.timeout,
                        )
                details.append(
                    "clip sent" if audio_response.status_code == 200
                    else "clip failed HTTP {}".format(audio_response.status_code)
                )
            else:
                details.append("no clip available")

            if latitude is not None and longitude is not None:
                location_response = requests.post(
                    self._url("sendLocation"),
                    data={"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
                    timeout=self.timeout,
                )
                details.append(
                    "location pin sent" if location_response.status_code == 200
                    else "location failed HTTP {}".format(location_response.status_code)
                )

            return "sent", "; ".join(details)
        except Exception as error:  # network failure must degrade, not crash
            return "failed", "Telegram request error: {}".format(error)

    def recent_chats(self, limit=20):
        """Lists chats that have messaged the bot (via getUpdates).

        This is how a contact registers: they open the bot and press Start,
        then the user picks their chat id in the app instead of copying a
        numeric id by hand.
        """
        if not self.configured:
            return []
        try:
            response = requests.get(
                self._url("getUpdates"), params={"limit": 100}, timeout=self.timeout
            )
            if response.status_code != 200:
                return []
            seen = {}
            for update in response.json().get("result", []):
                message = update.get("message") or update.get("edited_message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is None or chat_id in seen:
                    continue
                name = " ".join(
                    part for part in [chat.get("first_name"), chat.get("last_name")] if part
                ) or chat.get("title") or chat.get("username") or str(chat_id)
                seen[chat_id] = {
                    "chat_id": str(chat_id),
                    "name": name,
                    "username": chat.get("username"),
                    "type": chat.get("type"),
                }
            return list(seen.values())[:limit]
        except Exception:
            return []


def build_twiml(script, clip_url=None, repeat=2):
    """TwiML document spoken to the contact, then the evidence clip.

    Repeated twice: someone who answers a call mid-sentence should still hear
    the whole thing without needing to call back.
    """
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    for index in range(max(1, repeat)):
        parts.append('  <Say voice="alice">' + saxutils.escape(script) + "</Say>")
        if clip_url:
            parts.append("  <Play>" + saxutils.escape(clip_url) + "</Play>")
        if index == 0 and repeat > 1:
            parts.append('  <Pause length="1"/>')
    parts.append('  <Say voice="alice">End of Echo alert. Goodbye.</Say>')
    parts.append("</Response>")
    return "\n".join(parts)


class VoiceCaller:
    """Places the automated voice call through Twilio's REST API."""

    def __init__(self, account_sid=None, auth_token=None, from_number=None,
                 api_base=None, public_base_url=None, timeout=None):
        self.account_sid = account_sid if account_sid is not None else settings.twilio_account_sid
        self.auth_token = auth_token if auth_token is not None else settings.twilio_auth_token
        self.from_number = from_number if from_number is not None else settings.twilio_from_number
        self.api_base = (api_base or settings.twilio_api_base).rstrip("/")
        self.public_base_url = (
            public_base_url if public_base_url is not None else settings.public_base_url
        ).rstrip("/")
        self.timeout = timeout or settings.request_timeout_seconds

    @property
    def configured(self):
        return bool(
            self.account_sid and self.auth_token and self.from_number and self.public_base_url
        )

    def twiml_url(self, incident_id):
        return "{}/incidents/{}/twiml".format(self.public_base_url, incident_id)

    def clip_url(self, incident_id):
        return "{}/incidents/{}/clip".format(self.public_base_url, incident_id)

    def place_call(self, to_number, incident_id, script):
        """Returns (status, detail). status is sent | simulated | failed."""
        if not to_number:
            return "failed", "Contact has no phone number saved."
        to_clean = "".join(c for c in str(to_number).strip() if c.isdigit() or c == "+")
        if not to_clean.startswith("+"):
            if len(to_clean) == 10:
                to_number = "+91" + to_clean
            else:
                to_number = "+" + to_clean
        else:
            to_number = to_clean
        if not self.configured:
            missing = []
            if not self.account_sid or not self.auth_token:
                missing.append("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN")
            if not self.from_number:
                missing.append("TWILIO_FROM_NUMBER")
            if not self.public_base_url:
                missing.append("ECHO_PUBLIC_BASE_URL")
            return "simulated", (
                "Voice call not configured (" + ", ".join(missing) + "). "
                "Would have called " + str(to_number) + " and said: " + script
            )

        try:
            response = requests.post(
                "{}/2010-04-01/Accounts/{}/Calls.json".format(self.api_base, self.account_sid),
                auth=(self.account_sid, self.auth_token),
                data={
                    "To": to_number,
                    "From": self.from_number,
                    "Url": self.twiml_url(incident_id),
                    },
                timeout=self.timeout,
            )
            if response.status_code in (200, 201):
                call_sid = response.json().get("sid", "unknown")
                return "sent", "Call queued (sid {}) to {}".format(call_sid, to_number)
            return "failed", "Twilio HTTP {}: {}".format(
                response.status_code, response.text[:200]
            )
        except Exception as error:
            return "failed", "Twilio request error: {}".format(error)


