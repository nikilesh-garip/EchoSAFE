import time
from risk_scorer import RiskScorer

def test_risk_scorer():
    print("Testing Risk Scorer Engine...")
    
    # 1. Normal conversation test
    scorer = RiskScorer()
    score, level = scorer.calculate_risk(
        primary_conf=0.1,
        verification_conf=0.1,
        media_playback=False,
        sudden_motion=False,
        current_class="normal"
    )
    print(f"Normal: Score={score}, Level={level}")
    assert score == 7, f"Expected 7, got {score}"
    assert level == "NORMAL", f"Expected NORMAL, got {level}"
    
    # 2. Isolated weak gunshot candidate
    score, level = scorer.calculate_risk(
        primary_conf=0.55,
        verification_conf=0.45,
        media_playback=False,
        sudden_motion=False,
        current_class="gunshot"
    )
    print(f"Weak Gunshot: Score={score}, Level={level}")
    assert score == 35, f"Expected 35, got {score}"
    assert level == "SUSPICIOUS", f"Expected SUSPICIOUS, got {level}"

    # Reset scorer to avoid influence of history
    scorer = RiskScorer()
    
    # 3. Strong verified gunshot
    score, level = scorer.calculate_risk(
        primary_conf=0.95,
        verification_conf=0.90,
        media_playback=False,
        sudden_motion=True,
        current_class="gunshot"
    )
    print(f"Strong Verified Gunshot: Score={score}, Level={level}")
    assert score == 80, f"Expected 80, got {score}"
    assert level == "POSSIBLE_DANGER", f"Expected POSSIBLE_DANGER, got {level}"

    # Reset scorer
    scorer = RiskScorer()

    # 4. Movie/media gunshot
    score, level = scorer.calculate_risk(
        primary_conf=0.95,
        verification_conf=0.90,
        media_playback=True,
        sudden_motion=False,
        current_class="gunshot"
    )
    print(f"Movie Gunshot: Score={score}, Level={level}")
    assert score == 40, f"Expected 40, got {score}"
    assert level == "SUSPICIOUS", f"Expected SUSPICIOUS, got {level}"

    # Reset scorer
    scorer = RiskScorer()

    # 5. Distress scream
    score, level = scorer.calculate_risk(
        primary_conf=0.85,
        verification_conf=0.80,
        media_playback=False,
        sudden_motion=True,
        current_class="scream"
    )
    print(f"Distress Scream: Score={score}, Level={level}")
    assert score == 73, f"Expected 73, got {score}"
    assert level == "POSSIBLE_DANGER", f"Expected POSSIBLE_DANGER, got {level}"

    # 6. Multi-event dangerous sequence (Accumulating Temporal History)
    scorer = RiskScorer()
    
    # Event 1: Gunshot
    score1, level1 = scorer.calculate_risk(
        primary_conf=0.80,
        verification_conf=0.80,
        media_playback=False,
        sudden_motion=True,
        current_class="gunshot"
    )
    print(f"Seq Event 1 (Gunshot): Score={score1}, Level={level1}")
    assert score1 == 71, f"Expected 71, got {score1}"
    
    # Event 2: Scream (within 1s)
    score2, level2 = scorer.calculate_risk(
        primary_conf=0.80,
        verification_conf=0.80,
        media_playback=False,
        sudden_motion=True,
        current_class="scream"
    )
    print(f"Seq Event 2 (Scream): Score={score2}, Level={level2}")
    assert score2 == 81, f"Expected 81, got {score2}"
    
    # Event 3: Shouting (within 2s)
    score3, level3 = scorer.calculate_risk(
        primary_conf=0.90,
        verification_conf=0.90,
        media_playback=False,
        sudden_motion=True,
        current_class="shouting"
    )
    print(f"Seq Event 3 (Shouting): Score={score3}, Level={level3}")
    assert score3 == 98, f"Expected 98, got {score3}"
    assert level3 == "HIGH_RISK", f"Expected HIGH_RISK, got {level3}"

    # A sequence belongs to its monitoring session, never another user's session.
    scorer = RiskScorer()
    scorer.calculate_risk(0.8, 0.8, False, False, "gunshot", context_id="user_a")
    score, _ = scorer.calculate_risk(0.8, 0.8, False, False, "scream", context_id="user_b")
    assert score == 56, f"Expected isolated session score 56, got {score}"
    
    print("All Risk Scorer Unit Tests Passed Successfully!")

if __name__ == "__main__":
    test_risk_scorer()
