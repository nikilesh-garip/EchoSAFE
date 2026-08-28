"""Runtime configuration for Echo's emergency-escalation layer.

Everything here is read from the process environment, optionally seeded from a
`.env` file next to this module (see `.env.example`). No secret is ever
hardcoded, committed, or returned by an API route -- `public_status()` exposes
only whether a channel is configured, never the credential itself.

If a channel is not configured the escalation still runs in **simulation
mode**: the exact message, call script, and recipient are recorded in the
incident's escalation log and returned to the app, but nothing leaves the
machine. That keeps the demo honest (the UI says "simulated") and keeps the
pipeline testable without live credentials.
"""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"


def _load_dotenv(path: Path = ENV_PATH) -> None:
    """Minimal KEY=VALUE .env loader (no dependency on python-dotenv).

    Existing environment variables always win, so a real deployment can
    override the file without editing it.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


class Settings:
    """Snapshot of escalation configuration, re-read on demand in tests."""

    def __init__(self):
        self.reload()

    def reload(self):
        # --- Telegram ---------------------------------------------------
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_api_base = os.environ.get(
            "TELEGRAM_API_BASE", "https://api.telegram.org"
        ).rstrip("/")

        # --- Automated voice call (Twilio REST, no SDK dependency) ------
        self.twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self.twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        self.twilio_from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
        self.twilio_api_base = os.environ.get(
            "TWILIO_API_BASE", "https://api.twilio.com"
        ).rstrip("/")

        # Publicly reachable base URL of this backend. Twilio fetches the
        # TwiML document and the 5-second evidence clip from here, so a
        # localhost URL cannot work for a real call (use an ngrok/cloudflared
        # tunnel). Without it, voice calls stay in simulation mode.
        self.public_base_url = os.environ.get("ECHO_PUBLIC_BASE_URL", "").strip().lstrip("=").strip().rstrip("/")

        # --- Escalation policy ------------------------------------------
        self.escalation_enabled = _flag("ECHO_ESCALATION_ENABLED", True)
        # Seconds the user has to cancel before contacts are called/messaged.
        # A model result is evidence, not proof -- the person in the room gets
        # the last word before anyone's phone rings.
        self.cancel_window_seconds = _number("ECHO_CANCEL_WINDOW_SECONDS", 12.0)
        # Minimum risk score that may auto-escalate at all.
        self.min_risk_score = _number("ECHO_MIN_ESCALATION_RISK", 61)
        # Per-user cooldown so one noisy environment cannot dial a contact
        # every eight seconds.
        self.cooldown_seconds = _number("ECHO_ESCALATION_COOLDOWN_SECONDS", 120.0)
        # Evidence clip retention (seconds). Clips are the most sensitive
        # artifact this system stores, so they expire by default.
        self.clip_retention_seconds = _number("ECHO_CLIP_RETENTION_SECONDS", 7 * 24 * 3600)
        self.clip_seconds = _number("ECHO_CLIP_SECONDS", 5.0)
        self.request_timeout_seconds = _number("ECHO_HTTP_TIMEOUT_SECONDS", 20.0)

    # --- Derived capability flags ---------------------------------------
    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def voice_configured(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
            and self.public_base_url
        )

    def public_status(self) -> dict:
        """Capability report safe to return over the API (no secrets)."""
        return {
            "escalation_enabled": self.escalation_enabled,
            "telegram_configured": self.telegram_configured,
            "voice_call_configured": self.voice_configured,
            "public_base_url_set": bool(self.public_base_url),
            "cancel_window_seconds": self.cancel_window_seconds,
            "min_risk_score": self.min_risk_score,
            "cooldown_seconds": self.cooldown_seconds,
            "clip_seconds": self.clip_seconds,
            "simulation_mode": not (self.telegram_configured or self.voice_configured),
        }


settings = Settings()

