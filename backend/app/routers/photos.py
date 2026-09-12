"""Serving uploaded photos.

Photos used to be a plain ``StaticFiles`` mount, which meant anyone holding a
URL could fetch a garment's photo without logging in at all. The filenames are
random UUIDs so they cannot be guessed, but a link that leaks — via browser
history, a copied URL, a referrer — bypassed the wardrobe sharing rules
entirely. Every photo now goes through the same access check as the garment it
belongs to.

An ``<img>`` tag cannot send an Authorization header, so alongside the header
this route also accepts a cookie, set at login and scoped to this path.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..access import require_view
from ..config import settings
from ..database import get_db
from ..deps import user_for_token
from ..models import Item, User

router = APIRouter(tags=["photos"])

#: Path-scoped so it travels with photo requests and nothing else.
PHOTO_COOKIE = "wardrobe_photo"
COOKIE_PATH = "/uploads"


def is_https(request: Request | None) -> bool:
    """Whether the browser reached us over https, as far as we can tell."""
    if request is None:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return (forwarded or request.url.scheme) == "https"


def wants_secure_cookie(request: Request | None) -> bool:
    """Whether to mark cookies Secure.

    "auto" is the default and decides per request, because both answers are
    wrong as a constant: on plain http — which is how plenty of home networks
    serve this — a Secure cookie is simply never sent and every photo breaks,
    while on https leaving it off hands the token to anyone who can make the
    browser try http once.
    """
    setting = settings.cookie_secure.strip().lower()
    if setting in ("1", "true", "yes", "on"):
        return True
    if setting in ("0", "false", "no", "off"):
        return False
    return is_https(request)


def set_photo_cookie(response: Response, token: str, request: Request | None = None) -> None:
    """Hand the browser the credential its <img> requests will need."""
    response.set_cookie(
        PHOTO_COOKIE,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        path=COOKIE_PATH,
        secure=wants_secure_cookie(request),
    )


def clear_photo_cookie(response: Response) -> None:
    response.delete_cookie(PHOTO_COOKIE, path=COOKIE_PATH)


def _current_user(request: Request, db: Session) -> User:
    """Authenticate a photo request from the header, else from the cookie.

    Both go through the same check as every other request, so a token that has
    been revoked stops serving photos at the same moment it stops serving data.
    """
    token = None
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        token = request.cookies.get(PHOTO_COOKIE)
    user = user_for_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Niet ingelogd of sessie verlopen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/uploads/{filename}")
def photo(filename: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)

    item = (
        db.query(Item)
        .filter(or_(Item.photo_filename == filename, Item.thumb_filename == filename))
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Foto niet gevonden")
    require_view(db, item.wardrobe_id, user)

    path = (settings.uploads_dir / filename).resolve()
    # The route captures a single segment, but resolve the path anyway and
    # refuse anything that climbed out of the uploads directory.
    if path.parent != settings.uploads_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Foto niet gevonden")

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            # The filename carries a UUID, so an edited photo is a different
            # URL and this one can never go stale. "private" keeps it out of
            # any shared proxy on the way.
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )
