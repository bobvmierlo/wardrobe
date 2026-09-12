import io
import shutil
import uuid

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from .config import settings
from .fetching import FetchFailed, FetchRefused, fetch_remote

MAX_DIM = 1280       # longest side of the stored full photo
THUMB_DIM = 400      # longest side of the thumbnail


def _save_jpeg(img: Image.Image, path, quality: int) -> None:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(path, format="JPEG", quality=quality, optimize=True)


def _store_bytes(raw: bytes) -> tuple[str, str]:
    """Process raw image bytes into a stored photo + thumbnail.

    The image is EXIF-rotated, downscaled and re-encoded as JPEG so the
    wardrobe stays lightweight regardless of what the phone camera produced.
    """
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Foto is te groot (max {settings.max_upload_mb} MB)")
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except Exception:
        raise HTTPException(status_code=400, detail="Ongeldig afbeeldingsbestand")

    stem = uuid.uuid4().hex
    photo_name = f"{stem}.jpg"
    thumb_name = f"{stem}_thumb.jpg"

    full = img.copy()
    full.thumbnail((MAX_DIM, MAX_DIM))
    _save_jpeg(full, settings.uploads_dir / photo_name, quality=85)

    thumb = img.copy()
    thumb.thumbnail((THUMB_DIM, THUMB_DIM))
    _save_jpeg(thumb, settings.uploads_dir / thumb_name, quality=80)

    return photo_name, thumb_name


def store_image_bytes(raw: bytes) -> tuple[str, str]:
    """Store raw image bytes, returning (photo_filename, thumb_filename).

    Used when a photo arrives from inside a backup archive rather than from a
    browser upload. It goes through the same processing as any upload, which
    doubles as validation: bytes that are not a real image never reach disk.
    """
    return _store_bytes(raw)


def save_upload(file: UploadFile) -> tuple[str, str]:
    """Store an uploaded image, returning (photo_filename, thumb_filename)."""
    return _store_bytes(file.file.read())


def save_upload_from_url(url: str) -> tuple[str, str]:
    """Download an image from a URL and store it like a normal upload.

    The URL comes from whoever is adding the garment, so the fetch goes through
    :mod:`app.fetching` — which refuses to walk into the private network the
    server happens to be sitting on. See that module for what it does and does
    not guarantee.
    """
    try:
        fetched = fetch_remote(
            url,
            limit=settings.max_upload_mb * 1024 * 1024,
            headers={"User-Agent": "Mozilla/5.0 (Kledingkast)"},
        )
    except FetchRefused as exc:
        # A refusal by policy, so say which: "kon niet downloaden" would send
        # someone hunting for a network problem that is not there.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FetchFailed as exc:
        raise HTTPException(
            status_code=400, detail=f"Kon de afbeelding niet downloaden: {exc}"
        ) from exc
    return _store_bytes(fetched.body)


def copy_photo(
    photo_filename: str | None, thumb_filename: str | None
) -> tuple[str | None, str | None]:
    """Copy a stored photo + thumbnail to fresh filenames (for duplicating an
    item), so the copy owns its own files and deleting one never affects the
    other. Returns (None, None) when there is nothing to copy or it fails."""
    if not photo_filename:
        return None, None
    stem = uuid.uuid4().hex
    new_photo = f"{stem}.jpg"
    new_thumb = f"{stem}_thumb.jpg" if thumb_filename else None
    try:
        shutil.copyfile(settings.uploads_dir / photo_filename, settings.uploads_dir / new_photo)
        if thumb_filename and new_thumb:
            shutil.copyfile(settings.uploads_dir / thumb_filename, settings.uploads_dir / new_thumb)
    except OSError:
        return None, None
    return new_photo, new_thumb


def delete_files(*filenames: str | None) -> None:
    for name in filenames:
        if not name:
            continue
        target = settings.uploads_dir / name
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
