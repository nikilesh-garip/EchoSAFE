from safety_policy import decide_action


def test_safety_policy():
    assert decide_action(verified=False, class_name="gunshot", risk_score=99,
                         media_playback=False, sudden_motion=False, repeat_count=0).state == "MONITORING"
    assert decide_action(verified=True, class_name="gunshot", risk_score=70,
                         media_playback=True, sudden_motion=False, repeat_count=0).state == "LIKELY_PLAYBACK_REVIEW"
    assert decide_action(verified=True, class_name="gunshot", risk_score=70,
                         media_playback=True, sudden_motion=True, repeat_count=0).state == "URGENT_USER_ACTION"
    assert decide_action(verified=True, class_name="scream", risk_score=45,
                         media_playback=False, sudden_motion=False, repeat_count=0).state == "REVIEW_NOW"
    print("Safety policy tests passed.")


def test_movie_gunshot_scenario_is_reviewed_not_alarmed():
    # The exact scenario this was built for: a gunshot detected while the
    # room acoustically sounds like it has a movie/TV playing (media_playback
    # here may come from the user's manual toggle or from the automatic
    # acoustic media-context signal in audio_classes.py -- both funnel
    # through this same boolean). It must not fire an urgent alarm, but it
    # must still remain reviewable, not silently dropped.
    decision = decide_action(
        verified=True, class_name="gunshot", risk_score=70,
        media_playback=True, sudden_motion=False, repeat_count=0,
        context_source="acoustic_signal",
    )
    assert decision.state == "LIKELY_PLAYBACK_REVIEW"
    assert decision.offer_emergency_handoff is False
    assert decision.show_guidance is True
    assert decision.context_reliability == "acoustic_signal"


def test_movie_gunshot_scenario_still_alarms_if_evidence_conflicts():
    # If the user is also running (sudden_motion) despite the movie-like
    # audio context, that conflicting evidence must win -- a real emergency
    # during a movie must not be silently swallowed by the playback signal.
    decision = decide_action(
        verified=True, class_name="gunshot", risk_score=70,
        media_playback=True, sudden_motion=True, repeat_count=0,
        context_source="acoustic_signal",
    )
    assert decision.state == "URGENT_USER_ACTION"


if __name__ == "__main__":
    test_safety_policy()
    test_movie_gunshot_scenario_is_reviewed_not_alarmed()
    test_movie_gunshot_scenario_still_alarms_if_evidence_conflicts()
