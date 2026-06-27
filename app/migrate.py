"""One-time migration of legacy single-user data into per-user storage.

Filled in P1. For now this is a no-op stub so the auth registration hook has a
stable import target.
"""
from __future__ import annotations

from .models import UserRecord


def inherit_legacy_if_eligible(user: UserRecord) -> None:
    """Give the legacy single-user artifacts to the inheriting account.

    P1 will move <data_dir>/users/_legacy/ to this user's dir when they are the
    designated admin (settings.admin_email) or the first registrant.
    """
    return None
