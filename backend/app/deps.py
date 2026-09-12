"""Who is making this request.

One place decides what a token means, because there are two doors it arrives
through — the ``Authorization`` header on every API call, and the cookie an
``<img>`` has to use for photos — and they must never disagree about whether a
token is still alive.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def user_for_token(db: Session, token: str | None) -> User | None:
    """The account a token belongs to, or None when it is not (or no longer) valid.

    "No longer" is the part worth having: a token also dies when the account's
    ``token_version`` has moved past the one stamped into it, which is how a
    password change ends the sessions that knew the old password instead of
    leaving them running for another thirty days.
    """
    if not token:
        return None
    decoded = decode_token(token)
    if decoded is None:
        return None
    subject, version = decoded
    try:
        user = db.get(User, int(subject))
    except (TypeError, ValueError):
        return None
    if user is None or user.token_version != version:
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = user_for_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niet ingelogd of sessie verlopen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Alleen voor beheerders")
    return user
