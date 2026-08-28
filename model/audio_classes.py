"""Shared class constants for the Echo hazard classifier.

Single source of truth for the 8-class taxonomy, replacing the CNN-Transformer
era's dataset.py CLASS_MAPPING (removed along with the CNN-Transformer model).
"""

CLASS_MAPPING = {
    "normal": 0,
    "gunshot": 1,
    "explosion": 2,
    "scream": 3,
    "glass_breaking": 4,
    "fire_alarm": 5,
    "siren": 6,
    "shouting": 7,
}
IDX_TO_CLASS = {v: k for k, v in CLASS_MAPPING.items()}
NUM_CLASSES = len(CLASS_MAPPING)
SAMPLE_RATE = 16000

# --- Demo profile taxonomy -------------------------------------------------
# The demo profile adds one class the production taxonomy deliberately does
# not have: "firecracker" (Diwali crackers, chain "ladi" bursts, aerial
# shells). Two reasons it is a *separate class* rather than extra gunshot
# training data:
#   1. The production model must keep treating a firecracker as NOT a gunshot;
#      polluting the real head with cracker audio would trade away exactly the
#      false-positive resistance that makes the system defensible.
#   2. In the demo the cracker must reliably drive the full alert path, and a
#      dedicated class can be detected far more accurately than hoping a
#      gunshot classifier misfires on the right sound.
# At inference the demo profile aliases firecracker -> gunshot for risk
# scoring and escalation, while the response keeps `raw_class="firecracker"`
# so nothing in the logs, the Telegram message, or the incident record claims
# a real gunshot was heard.
DEMO_CLASS_MAPPING = dict(CLASS_MAPPING)
DEMO_CLASS_MAPPING["firecracker"] = len(CLASS_MAPPING)
DEMO_IDX_TO_CLASS = {v: k for k, v in DEMO_CLASS_MAPPING.items()}
DEMO_NUM_CLASSES = len(DEMO_CLASS_MAPPING)

# Class produced by the demo head -> class the rest of the system reasons about.
DEMO_ALIAS_MAP = {"firecracker": "gunshot"}


YAMNET_HANDLE = "https://tfhub.dev/google/yamnet/1"

# AudioSet label indices (from YAMNet's own 521-class ontology) that indicate
# recorded/broadcast media rather than a live in-room sound. This is a real
# acoustic signal -- not the manual "media playback" toggle -- but it is
# still weak evidence, not proof: a television playing a gunshot scene and a
# television playing a nature documentary both trip "Television"/"Music".
# It is used exactly like the platform_signal context source already defined
# in safety_policy.py: it can lower urgency, it never silently drops an
# event, and a conflicting signal (sudden motion, a hazard sequence) still
# wins. See docs/SAFETY_IMPLEMENTATION_PLAN.md's "Gunshot versus playback"
# section for why audio alone can never fully resolve this.
MEDIA_CONTEXT_AUDIOSET_INDICES = {
    132: "Music",
    262: "Background music",
    263: "Theme music",
    265: "Soundtrack music",
    267: "Video game music",
    276: "Scary music",
    518: "Television",
    519: "Radio",
}

# Threshold above which the acoustic media-context signal is treated as
# equivalent to a user/platform "media playback active" report.
MEDIA_CONTEXT_THRESHOLD = 0.15
