"""Downloading and restoring back-ups.

Who may do what:

* **Iedereen** may export a kast they can see — their own, or one shared with
  them. That file is theirs to keep: a spreadsheet, the photos, and the data a
  restore needs.
* **Beheerders** may additionally export the whole installation, take a raw
  momentopname of the database, and put an archive back.

Restoring is deliberately kept to beheerders. It writes over garments and
verdicts that may belong to several people, which is not a button an ordinary
user should find under their own settings.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .. import audit, backup
from ..access import require_view
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..logging_setup import get_logger
from ..models import User, Wardrobe

log = get_logger("backup")

router = APIRouter(prefix="/api/backup", tags=["backup"])

ZIP_MIME = "application/zip"

#: An uploaded archive is streamed to disk in chunks, never read into memory
#: whole: a full-instance backup can be hundreds of megabytes.
UPLOAD_CHUNK = 1024 * 1024
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


def _cleanup(path: Path) -> BackgroundTask:
    """Delete the temporary file once the response has been sent."""

    def remove() -> None:
        path.unlink(missing_ok=True)

    return BackgroundTask(remove)


def _download(path: Path, filename: str) -> FileResponse:
    return FileResponse(
        path,
        media_type=ZIP_MIME,
        filename=filename,
        background=_cleanup(path),
        # Without this the browser cannot read the name off a fetch() response.
        headers={"Access-Control-Expose-Headers": "Content-Disposition"},
    )


@router.get("/wardrobe/{wardrobe_id}")
def export_wardrobe(
    wardrobe_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export one kast: workbook, photos and the data behind them."""
    wardrobe, _role = require_view(db, wardrobe_id, user)
    payload, photos = backup.collect(db, [wardrobe], scope="wardrobe", actor=user)
    path = backup.write_archive(payload, photos)
    audit.record(
        db,
        "backup.export",
        f"Kast '{wardrobe.name}' geëxporteerd "
        f"({backup.counts_of(payload)['items']} kledingstukken)",
        user=user,
        wardrobe_id=wardrobe.id,
    )
    return _download(path, backup.safe_filename(wardrobe.name, ".zip"))


@router.get("/instance")
def export_instance(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export every kast at once, with the accounts and the catalogue."""
    wardrobes = db.query(Wardrobe).order_by(Wardrobe.id).all()
    payload, photos = backup.collect(
        db, wardrobes, scope="instance", actor=user, with_accounts=True
    )
    path = backup.write_archive(payload, photos)
    audit.record(
        db,
        "backup.export_full",
        f"Volledige back-up gemaakt ({backup.counts_of(payload)['items']} kledingstukken, "
        f"{len(wardrobes)} kasten)",
        user=user,
    )
    return _download(path, backup.safe_filename("volledig", ".zip"))


@router.get("/snapshot")
def export_snapshot(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """The raw database and uploads folder, for disaster recovery."""
    path = backup.write_snapshot()
    audit.record(db, "backup.snapshot", "Momentopname van de database gedownload", user=user)
    return _download(path, backup.safe_filename("momentopname", ".zip"))


def _receive(upload: UploadFile) -> Path:
    """Stream an uploaded archive to a temporary file, capped in size."""
    handle = tempfile.NamedTemporaryFile(prefix="kledingkast-restore-", suffix=".zip", delete=False)
    path = Path(handle.name)
    total = 0
    try:
        while chunk := upload.file.read(UPLOAD_CHUNK):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Het bestand is te groot.")
            handle.write(chunk)
    except HTTPException:
        handle.close()
        path.unlink(missing_ok=True)
        raise
    handle.close()
    return path


def _read(path: Path):
    try:
        return backup.read_archive(path)
    except backup.RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/inspect")
def inspect(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    """Say what is in an archive, without changing anything.

    The restore screen asks this first: nobody should have to click "terugzetten"
    to find out whether they picked the right file.
    """
    path = _receive(file)
    try:
        payload, photos = _read(path)
        return {
            "scope": payload.get("scope"),
            "app_version": payload.get("app_version"),
            "generated_at": payload.get("generated_at"),
            "generated_by": payload.get("generated_by"),
            "wardrobe_names": [w.get("name") for w in payload.get("wardrobes", [])],
            "photos": len(photos),
            **backup.counts_of(payload),
        }
    finally:
        path.unlink(missing_ok=True)


@router.post("/restore")
def restore(
    file: UploadFile = File(...),
    wardrobe_id: int = Form(...),
    mode: str = Form("merge"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Put an archive back into one kast, merging or replacing its contents."""
    if mode not in {"merge", "replace"}:
        raise HTTPException(status_code=400, detail="Kies samenvoegen of vervangen.")
    target = db.get(Wardrobe, wardrobe_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Kast niet gevonden")

    path = _receive(file)
    try:
        payload, photos = _read(path)
        try:
            stats = backup.apply_payload(
                db, payload, photos, mode=mode, target=target, actor=user
            )
        except backup.RestoreError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            # Nothing half-restored: either the whole archive lands or none of it.
            db.rollback()
            log.exception("Terugzetten van een back-up is mislukt")
            raise HTTPException(
                status_code=500,
                detail="Terugzetten is mislukt; er is niets gewijzigd.",
            )
        audit.record(
            db,
            "backup.restore",
            f"Back-up teruggezet in '{target.name}' "
            f"({'vervangen' if mode == 'replace' else 'samengevoegd'}): "
            f"{stats['added']} toegevoegd, {stats['updated']} bijgewerkt, "
            f"{stats['combinations']} combinaties",
            user=user,
            wardrobe_id=target.id,
            commit=False,
        )
        db.commit()
        return {"mode": mode, "wardrobe": target.name, **stats}
    finally:
        path.unlink(missing_ok=True)


@router.get("/wardrobes")
def restorable_wardrobes(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """The kasten a beheerder can restore into, for the target dropdown."""
    return [
        {"id": w.id, "name": w.name, "owner": w.owner.display_name}
        for w in db.query(Wardrobe).order_by(Wardrobe.name).all()
    ]
