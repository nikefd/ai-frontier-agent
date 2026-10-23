"""Regression tests for the intraday scheduler cadence."""

from app.scheduler import _cron_hours, _feeds_for_cadence, _scheduled_hours


def test_fetch_cadence_wraps_around_midnight() -> None:
    assert _scheduled_hours(5, 4) == (1, 5, 9, 13, 17, 21)
    assert _cron_hours(5, 4) == "1,5,9,13,17,21"


def test_summary_cadence_stays_one_hour_after_fetch() -> None:
    assert _scheduled_hours(6, 4) == (2, 6, 10, 14, 18, 22)


def test_daily_and_invalid_intervals_are_safe() -> None:
    assert _scheduled_hours(5, 24) == (5,)
    assert _scheduled_hours(5, 5) == (1, 5, 9, 13, 17, 21)


def test_source_cadences_are_disjoint_and_cover_registry() -> None:
    groups = {name: set(_feeds_for_cadence(name)) for name in ("fast", "standard", "slow")}
    assert groups["fast"]
    assert groups["standard"]
    assert groups["slow"]
    assert not (groups["fast"] & groups["standard"])
    assert not (groups["fast"] & groups["slow"])
    assert not (groups["standard"] & groups["slow"])
    assert sum(map(len, groups.values())) == 115
