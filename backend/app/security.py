from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGORITHM = "HS256"

#: Stored instead of a hash for an account that has no password of its own —
#: one created through a federated provider. A bcrypt hash always starts with
#: "$2", so this can never be matched by any password, and the check below
#: refuses it explicitly rather than relying on bcrypt to raise.
UNUSABLE_PASSWORD = "!sso"


def hash_password(password: str) -> str:
    # bcrypt operates on the first 72 bytes; encode explicitly.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    # An account that signs in through a provider has no local password. Such
    # a hash must never verify, whatever is typed into the form.
    if not hashed or not hashed.startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str | int, *, token_version: int) -> str:
    """Mint a login token for this account, stamped with its token version.

    ``token_version`` is required rather than defaulted: a token minted without
    the account's current version would be one that revocation cannot reach,
    and that is not a mistake worth making quietly.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject), "exp": expire, "tv": int(token_version)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> tuple[str, int] | None:
    """The (subject, token version) a token claims, or None if it is no good.

    A token from before versioning existed has no ``tv`` claim. Those count as
    version 1 — which is what every existing account is migrated to — so an
    upgrade does not sign the whole household out. The first password change
    moves that account to 2 and the old tokens die then, which is exactly when
    they should.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        version = int(payload.get("tv", 1))
    except (TypeError, ValueError):
        return None
    return str(sub), version
