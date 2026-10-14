"""Atomic JSON / SQLite helpers shared across routers.

Best-practice notes:
- All JSON writes go through `write_json_atomic` which writes to .tmp then renames,
  so a crashed process can never leave a half-written file (the openclaw upstream
  has hit this bug — see services/agents/server.js where every endpoint does its
  own JSON.stringify + writeFileSync). We do it once, centrally.
- SQLite access is read-only by default and uses URI mode so multiple readers
  can share a single file even when a writer (the finance scheduler) is active.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_FILE_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FILE_LOCKS[key] = lock
        return lock


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default
    except OSError:
        return default


def _write_text_unlocked(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile in same dir → atomic rename works across the same filesystem
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as f:
        tmp_name = f.name
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_name, path)


def write_text_atomic(path: Path, payload: str) -> None:
    lock = _lock_for(path)
    with lock:
        _write_text_unlocked(path, payload)


def write_json_atomic(path: Path, data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    write_text_atomic(path, payload)


def update_json_atomic(path: Path, default: T, mutator: Callable[[T], T]) -> T:
    """Atomically perform a JSON read-modify-write transaction for one path.

    Atomic rename alone prevents torn files but not lost updates. This helper
    holds the same per-path lock across the read, mutation and replacement.
    The mutator may raise; in that case nothing is written.
    """
    lock = _lock_for(path)
    with lock:
        data = read_json(path, default)
        updated = mutator(data)
        payload = json.dumps(updated, ensure_ascii=False, indent=2)
        _write_text_unlocked(path, payload)
        return updated


@contextmanager
def sqlite_ro(db_path: Path):
    """Read-only SQLite connection with row factory."""
    if not db_path.exists():
        # Return a connection to :memory: so callers get empty results, not crash
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
        return
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
