"""SM-2 spaced-repetition scheduler — pure functions, no IO.

Classic Anki-style SM-2 (https://super-memory.com/english/ol/sm2.htm), simplified
to a 3-button grading UI (forgot / hard / good) mapped to SM-2 quality scores.
Kept standalone so the algorithm is unit-testable without HTTP or storage.
"""
from __future__ import annotations

from datetime import date, timedelta

# 3-button UI → SM-2 quality (0..5). "forgot" lapses the card, the other two pass.
GRADES = {
    "forgot": 2,   # q < 3 → reset reps, short interval
    "hard": 3,     # passed but barely
    "good": 5,     # recalled cleanly
}

_DEFAULT_EASE = 2.5
_MIN_EASE = 1.3


def new_srs(today: str) -> dict:
    """Initial SRS state for a freshly created card (due immediately)."""
    return {"interval": 0, "ease": _DEFAULT_EASE, "reps": 0, "due": today, "last_review": None}


def sm2_schedule(srs: dict, grade: str, today: str) -> dict:
    """Return updated SRS state after a review graded `grade` on `today` (ISO date).

    Pure: does not mutate the input. `today` is injected (not read from a clock)
    so the function is deterministic and testable.
    """
    if grade not in GRADES:
        raise ValueError(f"invalid grade: {grade!r}")
    q = GRADES[grade]
    today_d = date.fromisoformat(today)

    ease = float(srs.get("ease", _DEFAULT_EASE))
    reps = int(srs.get("reps", 0))
    interval = int(srs.get("interval", 0))

    # Update ease factor per SM-2, floored at 1.3.
    ease = max(_MIN_EASE, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))

    if q < 3:
        # Lapse: restart the rep count, review again tomorrow.
        reps = 0
        interval = 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = round(interval * ease)
        interval = max(1, interval)

    due = (today_d + timedelta(days=interval)).isoformat()
    return {"interval": interval, "ease": round(ease, 2), "reps": reps,
            "due": due, "last_review": today}


def is_due(srs: dict, today: str) -> bool:
    """A card is due when its `due` date is on or before today."""
    due = srs.get("due")
    if not due:
        return True
    return due <= today
