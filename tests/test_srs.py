"""Tests for the SM-2 spaced-repetition scheduler (pure functions)."""
from app.srs import new_srs, sm2_schedule, is_due


def test_new_card_is_due_today():
    srs = new_srs("2026-06-28")
    assert is_due(srs, "2026-06-28")
    assert srs["reps"] == 0


def test_good_grades_grow_interval():
    srs = new_srs("2026-06-28")
    s1 = sm2_schedule(srs, "good", "2026-06-28")
    assert s1["reps"] == 1 and s1["interval"] == 1      # first pass → 1 day
    s2 = sm2_schedule(s1, "good", "2026-06-29")
    assert s2["reps"] == 2 and s2["interval"] == 6      # second pass → 6 days
    s3 = sm2_schedule(s2, "good", "2026-07-05")
    assert s3["interval"] > 6                            # then interval *= ease


def test_forgot_resets_reps_and_shortens():
    srs = new_srs("2026-06-28")
    s1 = sm2_schedule(srs, "good", "2026-06-28")
    s2 = sm2_schedule(s1, "good", "2026-06-29")
    lapsed = sm2_schedule(s2, "forgot", "2026-07-05")
    assert lapsed["reps"] == 0
    assert lapsed["interval"] == 1
    assert lapsed["due"] == "2026-07-06"


def test_ease_floored_at_1_3():
    srs = new_srs("2026-06-28")
    # Repeated "forgot" must not push ease below the 1.3 floor.
    for _ in range(10):
        srs = sm2_schedule(srs, "forgot", "2026-06-28")
    assert srs["ease"] >= 1.3


def test_due_date_comparison():
    srs = {"due": "2026-06-30"}
    assert not is_due(srs, "2026-06-29")
    assert is_due(srs, "2026-06-30")
    assert is_due(srs, "2026-07-01")


def test_invalid_grade_raises():
    try:
        sm2_schedule(new_srs("2026-06-28"), "bogus", "2026-06-28")
        assert False, "should have raised"
    except ValueError:
        pass
