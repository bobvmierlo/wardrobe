"""Settings a beheerder can change from inside the app.

:mod:`app.config` holds what the *operator* sets before the container starts
(paths, secrets, log level). This module holds what the *beheerder* changes
while it runs, stored in the ``app_settings`` table so a flip survives a
restart without anyone touching a compose file.

Values are plain strings on disk; every setting gets a typed accessor here so
the callers never parse anything themselves.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AppSetting

#: Whether anyone may create their own account from the login screen. Off by
#: default: the app is invitation-only until a beheerder says otherwise.
SELF_REGISTRATION = "self_registration"

_TRUE = {"1", "true", "yes", "on"}


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    return row.value.strip().lower() in _TRUE


def set_bool(db: Session, key: str, value: bool, *, commit: bool = True) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value="true" if value else "false"))
    else:
        row.value = "true" if value else "false"
    if commit:
        db.commit()


def self_registration_open(db: Session) -> bool:
    """True when the login screen may offer "account aanmaken"."""
    return get_bool(db, SELF_REGISTRATION, default=False)
