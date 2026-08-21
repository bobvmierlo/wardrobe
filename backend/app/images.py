import io
import uuid
from urllib.request import Request, urlopen

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from .config import settings

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


def save_upload(file: UploadFile) -> tuple[str, str]:
    """Store an uploaded image, returning (photo_filename, thumb_filename)."""
    return _store_bytes(file.file.read())


def save_upload_from_url(url: str) -> tuple[str, str]:
    """Download an image from a URL and store it like a normal upload."""
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Ongeldige afbeeldings-URL")
    limit = settings.max_upload_mb * 1024 * 1024
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Kledingkast)"})
        with urlopen(req, timeout=15) as resp:  # noqa: S310 (user-provided URL, size-capped)
            raw = resp.read(limit + 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Kon de afbeelding niet downloaden")
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail=f"Foto is te groot (max {settings.max_upload_mb} MB)")
    return _store_bytes(raw)


def delete_files(*filenames: str | None) -> None:
    for name in filenames:
        if not name:
            continue
        target = settings.uploads_dir / name
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
