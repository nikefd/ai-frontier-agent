"""One-time migration of legacy single-user data into per-user storage.

Two steps:
1. ``migrate_legacy_to_holding()`` runs at startup (idempotent): moves the old
   global user-owned artifacts (tracks.json / guides.json / guides/ / deep-dives/)
   out of ai-news/ into users/_legacy/, extracts pins from articles.json into
   users/_legacy/pins.json, strips the per-user ``pinned`` field from the global
   feed, and drops the synthetic "手动输入" manual articles (their deep-dive
   survives in _legacy/deep-dives/).
2. ``inherit_legacy_if_eligible(user)`` runs on registration: the designated
   admin (settings.admin_email) or the first registrant inherits users/_legacy/.

ui.db is intentionally left in place here; conversation isolation (P2) migrates
it so each phase ships self-consistent.
"""
from __future__ import annotations

import logging
import shutil

from .models import UserRecord
from .settings import settings
from .storage import read_json, write_json_atomic

log = logging.getLogger("aif.migrate")

USERS_DIR = settings.data_dir / "users"
LEGACY_DIR = USERS_DIR / "_legacy"
AINEWS_DIR = settings.data_dir / "ai-news"


def migrate_legacy_to_holding() -> None:
    """Move legacy single-user artifacts into users/_legacy/. Idempotent: once
    _legacy exists we never run again."""
    if LEGACY_DIR.exists():
        return

    tracks = AINEWS_DIR / "tracks.json"
    guides_json = AINEWS_DIR / "guides.json"
    guides_dir = AINEWS_DIR / "guides"
    deep_dives_dir = AINEWS_DIR / "deep-dives"
    articles_file = AINEWS_DIR / "articles.json"
    ui_db = AINEWS_DIR / "ui.db"

    articles = read_json(articles_file, [])
    if not isinstance(articles, list):
        articles = []
    pinned_ids = [a.get("id") for a in articles if a.get("pinned") and a.get("id")]
    has_manual = any(a.get("manual") or a.get("source") == "手动输入" for a in articles)

    has_legacy = (
        tracks.exists() or guides_json.exists() or guides_dir.exists()
        or deep_dives_dir.exists() or ui_db.exists() or pinned_ids or has_manual
    )
    if not has_legacy:
        return

    LEGACY_DIR.mkdir(parents=True, exist_ok=True)

    if tracks.exists():
        shutil.move(str(tracks), str(LEGACY_DIR / "tracks.json"))
    if guides_json.exists():
        shutil.move(str(guides_json), str(LEGACY_DIR / "guides.json"))
    if guides_dir.exists():
        shutil.move(str(guides_dir), str(LEGACY_DIR / "guides"))
    if deep_dives_dir.exists():
        shutil.move(str(deep_dives_dir), str(LEGACY_DIR / "deep-dives"))
    if ui_db.exists():
        # Conversation memory becomes the inheriting user's ui.db.
        shutil.move(str(ui_db), str(LEGACY_DIR / "ui.db"))

    if pinned_ids:
        write_json_atomic(LEGACY_DIR / "pins.json", sorted(set(pinned_ids)))

    # Clean the global feed: drop manual synthetic articles + strip per-user state.
    cleaned = []
    for a in articles:
        if a.get("manual") or a.get("source") == "手动输入":
            continue
        for k in ("pinned", "deep_dive_status", "deep_dive_id"):
            a.pop(k, None)
        cleaned.append(a)
    if cleaned != articles:
        write_json_atomic(articles_file, cleaned)

    log.warning("migrated legacy single-user data → %s (pins=%d, dropped_manual=%s)",
                LEGACY_DIR, len(pinned_ids), has_manual)


def _is_eligible(user: UserRecord) -> bool:
    if user.role != "admin":
        return False
    if settings.admin_email:
        return user.email == settings.admin_email
    # No designated email → the locally initialized admin inherits.
    return user.role == "admin"


def inherit_legacy_if_eligible(user: UserRecord) -> None:
    """Give the legacy single-user artifacts to the inheriting account."""
    if not LEGACY_DIR.exists():
        return
    if not _is_eligible(user):
        return

    target = USERS_DIR / user.id
    if not target.exists():
        shutil.move(str(LEGACY_DIR), str(target))
    else:
        # Target already has data (unlikely right after register) → merge files.
        for child in LEGACY_DIR.iterdir():
            dest = target / child.name
            if dest.exists():
                continue
            shutil.move(str(child), str(dest))
        shutil.rmtree(LEGACY_DIR, ignore_errors=True)

    log.warning("user %s (%s) inherited legacy single-user data → %s",
                user.id, user.email, target)
