"""Conservative policy for turning acoustic inference into user-facing actions.

This module deliberately does not dispatch police, ambulance, or fire services. An
acoustic model cannot establish an emergency with the certainty required for an
automated emergency call. It can notify the user, show guidance, and offer a
user-initiated emergency handoff.
"""

from dataclasses import asdict, dataclass


URGENT_HAZARDS = {"gunshot", "explosion", "fire_alarm"}


@dataclass(frozen=True)
class SafetyDecision:
    state: str
    should_notify: bool
    show_guidance: bool
    offer_emergency_handoff: bool
    rationale: str
    context_reliability: str

    def to_dict(self):
        return asdict(self)


CONTEXT_RELIABILITY = {
    "browser_manual": "manual",
    "platform_signal": "platform_signal",
    # Auto-detected from YAMNet's own general AudioSet predictions (e.g.
    # "Television"/"Music"/"Soundtrack music" concurrent with the hazard
    # sound) -- see audio_classes.MEDIA_CONTEXT_AUDIOSET_INDICES. Weaker than
    # a platform playback-capture signal: it is evidence the room *sounds*
    # like it has media playing, not proof of what device state says.
    "acoustic_signal": "acoustic_signal",
}


def decide_action(*, verified, class_name, risk_score, media_playback,
                  sudden_motion, repeat_count, context_source="browser_manual"):
    """Return a conservative action state without claiming incident certainty."""
    if context_source not in CONTEXT_RELIABILITY:
        # Silently falling back to a default reliability tier would mislabel
        # where this evidence came from -- in a safety decision, an unknown
        # context source must fail loudly, not get quietly relabeled as
        # "platform_signal".
        raise ValueError(
            f"Unrecognized context_source '{context_source}'; expected one of "
            f"{sorted(CONTEXT_RELIABILITY)}."
        )
    context_reliability = CONTEXT_RELIABILITY[context_source]

    if not verified:
        return SafetyDecision(
            "MONITORING", False, False, False,
            "The sound did not pass verification.", context_reliability,
        )

    # Playback is weak evidence. It suppresses interruption only when there is no
    # conflicting motion or sequence evidence; the event must remain reviewable.
    if media_playback and not sudden_motion and repeat_count == 0:
        return SafetyDecision(
            "LIKELY_PLAYBACK_REVIEW", False, True, False,
            "Verified sound occurred while playback was reported; review it instead of assuming it is safe.",
            context_reliability,
        )

    if risk_score >= 81 or (class_name in URGENT_HAZARDS and risk_score >= 61):
        return SafetyDecision(
            "URGENT_USER_ACTION", True, True, True,
            "Verified high-risk audio needs immediate user assessment. Emergency contact remains user initiated.",
            context_reliability,
        )

    if risk_score >= 31:
        return SafetyDecision(
            "REVIEW_NOW", True, True, False,
            "Verified audio needs attention, but evidence is below the emergency-handoff threshold.",
            context_reliability,
        )

    return SafetyDecision(
        "LOG_ONLY", False, True, False,
        "Verified audio was recorded for review at a low risk score.", context_reliability,
    )
