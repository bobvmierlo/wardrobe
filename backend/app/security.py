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


def create_access_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
