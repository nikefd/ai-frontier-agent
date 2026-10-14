"""Tests for the per-user daily LLM quota logic."""
import importlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor


def _fresh(limit=3):
    os.environ["AIF_DATA_DIR"] = tempfile.mkdtemp(prefix="aif-usage-test-")
    os.environ["AIF_DAILY_LLM_LIMIT"] = str(limit)
    import app.settings as s
    importlib.reload(s)
    import app.usage as u
    importlib.reload(u)
    return u


def test_counts_and_blocks_at_limit():
    u = _fresh(limit=3)
    uid = "u_test"
    assert u.usage_today(uid) == 0
    assert u.has_quota(uid)
    u.record_use(uid); u.record_use(uid); u.record_use(uid)
    assert u.usage_today(uid) == 3
    assert not u.has_quota(uid)          # hit limit
    assert u.remaining(uid) == 0


def test_remaining_decrements():
    u = _fresh(limit=50)
    uid = "u_r"
    u.record_use(uid)
    assert u.remaining(uid) == 49


def test_zero_limit_is_unlimited():
    u = _fresh(limit=0)
    uid = "u_unl"
    for _ in range(100):
        u.record_use(uid)
    assert u.has_quota(uid)              # never blocks
    assert u.remaining(uid) is None


def test_stale_date_resets():
    u = _fresh(limit=3)
    uid = "u_stale"
    # Simulate yesterday's usage by writing directly.
    from app.storage import write_json_atomic
    write_json_atomic(u._usage_file(uid), {"date": "2000-01-01", "count": 3})
    assert u.usage_today(uid) == 0       # stale day → counted as 0
    assert u.has_quota(uid)


def test_concurrent_consumption_never_exceeds_limit():
    u = _fresh(limit=7)
    uid = "u_concurrent"
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: u.consume_quota(uid), range(40)))
    assert sum(results) == 7
    assert u.usage_today(uid) == 7


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
