"""Read-only windows on what the app has been doing, for beheerders.

Two endpoints, two very different things:

* ``/api/audit`` — the durable trail of *who changed what*, straight from the
  ``audit_logs`` table. This is the answer to "wie heeft die combinatie
  goedgekeurd?".
* ``/api/logs`` — the last few hundred application log lines, the same ones
  ``docker compose logs`` shows. Volatile, technical, for troubleshooting.

Both are admin-only: they span every wardrobe in the installation.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..audit import label_for
from ..database import get_db
from ..deps import require_admin
from ..logging_setup import buffer_handler
from ..models import AuditLog, User, Wardrobe
from ..schemas import AuditEntryOut, AuditPage, LogEntryOut, UserOut  # noqa: F401

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/audit", response_model=AuditPage)
def audit_trail(
    action: str | None = None,
    user_id: int | None = None,
    wardrobe_id: int | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """The audit trail, newest first, with the filters the log screen offers."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if wardrobe_id is not None:
        query = query.filter(AuditLog.wardrobe_id == wardrobe_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(AuditLog.detail.ilike(like))

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    wardrobe_names = {w.id: w.name for w in db.query(Wardrobe).all()}
    actions = [
        a for (a,) in db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    ]
    return AuditPage(
        entries=[
            AuditEntryOut(
                id=r.id,
                created_at=r.created_at,
                action=r.action,
                action_label=label_for(r.action),
                user_id=r.user_id,
                user_name=r.user_name,
                wardrobe_id=r.wardrobe_id,
                wardrobe_name=wardrobe_names.get(r.wardrobe_id),
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                detail=r.detail,
            )
            for r in rows
        ],
        total=total,
        actions=actions,
    )


@router.get("/logs", response_model=list[LogEntryOut])
def app_logs(
    level: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    _: User = Depends(require_admin),
):
    """The most recent application log lines, newest first.

    Same content as the container log; kept in memory only, so it starts empty
    after a restart.
    """
    return [LogEntryOut(**entry) for entry in buffer_handler.snapshot(limit, level)]
