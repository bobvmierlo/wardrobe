import io
import uuid

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from .config import settings

MAX_DIM = 1280       # longest side of the stored full photo
THUMB_DIM = 400      # longest side of the thumbnail


def _save_jpeg(img: Image.Image, path, quality: int) -> None:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(path, format="JPEG", quality=quality, optimize=True)


def save_upload(file: UploadFile) -> tuple[str, str]:
    """Store an uploaded image, returning (photo_filename, thumb_filename).

    The image is EXIF-rotated, downscaled and re-encoded as JPEG so the
    wardrobe stays lightweight regardless of what the phone camera produced.
    """
    raw = file.file.read()
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


def delete_files(*filenames: str | None) -> None:
    for name in filenames:
        if not name:
            continue
        target = settings.uploads_dir / name
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
