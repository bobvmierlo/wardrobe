"""Making a backup without anyone having to remember.

The app has had a full-backup button and a snapshot button for a while. Nobody
clicks them weekly. That is not a discipline problem — it is what buttons are
like — and it means the honest description of the backup situation was "there
are backup buttons", which is a different thing from "there are backups".

So once a day, at a time the operator picks, the app writes a snapshot into
``/data/backups`` and throws away the oldest ones.

**Why a snapshot and not an export.** The export is the one the app can restore
through its own screens, which sounds like the better automatic choice. It is
not: a snapshot is a byte-exact copy of the database plus the photos, so it
restores *everything* — accounts, invitations, the audit trail, the catalogue —
where an export restores a kast's contents. When a disk dies, "everything" is the
only useful amount. It is also cheaper: :func:`app.backup.write_snapshot` uses
SQLite's own backup API rather than walking every garment through the ORM, which
is both faster and safe to do while the app is serving requests.

Restoring one is a file copy rather than an in-app action, and the README says
so. The in-app full export stays exactly where it was for the restorable
flavour.

**Why a time of day and not cron.** A cron expression needs either a dependency
or a parser nobody will read, to express schedules a household wardrobe will
never want. "Every day at 03:30" is the whole requirement. Anyone who genuinely
needs more can point a real cron at the existing endpoint.

The loop never dies. A backup that fails — a full disk, a locked database —
writes a loud line and waits for tomorrow, because a scheduler that gives up on
the first error is worse than no scheduler: it looks like it is working.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import audit, backup
from .config import settings
from .database import SessionLocal
from .logging_setup import get_logger

log = get_logger("backup")

#: Prefix every automatic backup shares, so rotation can recognise its own work
#: and never deletes something a person put in the folder.
PREFIX = "auto-"


@dataclass
class BackupFile:
    name: str
    size: int
    created_at: datetime

    @property
    def size_mb(self) -> float:
        return round(self.size / (1024 * 1024), 1)


def backups_dir() -> Path:
    """Where the automatic backups live. Created on demand."""
    path = settings.data_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups() -> list[BackupFile]:
    """The automatic backups on disk, newest first."""
    try:
        entries = [p for p in backups_dir().iterdir() if p.is_file() and p.name.startswith(PREFIX)]
    except OSError as exc:
        log.error("Kan de back-upmap niet lezen: %s", exc)
        return []
    files = []
    for path in entries:
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append(
            BackupFile(
                name=path.name,
                size=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime).astimezone(),
            )
        )
    return sorted(files, key=lambda f: f.created_at, reverse=True)


def resolve(name: str) -> Path | None:
    """The path of one automatic backup, or None for anything else.

    A name arriving from a URL must not be able to address a file outside this
    folder, so it is matched against what is actually there rather than joined
    onto a path.
    """
    if not name.startswith(PREFIX):
        return None
    for path in backups_dir().iterdir():
        if path.is_file() and path.name == name:
            return path
    return None


def parse_time(value: str) -> tuple[int, int] | None:
    """"03:30" → (3, 30). Anything unparseable turns the schedule off, loudly."""
    text = value.strip()
    if not text:
        return None
    try:
        hour_text, _, minute_text = text.partition(":")
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        log.error(
            "WARDROBE_BACKUP_TIME ('%s') is geen tijd in de vorm UU:MM —"
            " automatische back-ups staan uit.",
            value,
        )
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        log.error(
            "WARDROBE_BACKUP_TIME ('%s') valt buiten 00:00-23:59 —"
            " automatische back-ups staan uit.",
            value,
        )
        return None
    return hour, minute


def seconds_until(hour: int, minute: int, *, now: datetime | None = None) -> float:
    """How long until the next time it is ``hour:minute`` locally.

    Local rather than UTC, because "at half three at night" is what the operator
    means and the container's own clock is what they can see. Set ``TZ`` in the
    compose file to move it; the README says so.
    """
    current = now or datetime.now()
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return (target - current).total_seconds()


def rotate(keep: int) -> list[str]:
    """Delete all but the newest ``keep`` automatic backups. Returns what went."""
    if keep < 1:
        keep = 1
    removed: list[str] = []
    for stale in list_backups()[keep:]:
        path = backups_dir() / stale.name
        try:
            path.unlink()
            removed.append(stale.name)
        except OSError as exc:
            log.warning("Kon oude back-up %s niet verwijderen: %s", stale.name, exc)
    return removed


def run_once(*, reason: str = "automatisch") -> BackupFile:
    """Write one snapshot and rotate the old ones. Blocking; call in a thread."""
    started = datetime.now()
    temporary = backup.write_snapshot()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    destination = backups_dir() / f"{PREFIX}{stamp}.zip"
    try:
        # Move rather than copy: write_snapshot already wrote the bytes once, in
        # the system temp dir, and on the same filesystem this is a rename.
        shutil.move(str(temporary), destination)
    finally:
        Path(temporary).unlink(missing_ok=True)

    size = destination.stat().st_size
    removed = rotate(settings.backup_keep)
    elapsed = (datetime.now() - started).total_seconds()
    log.info(
        "Back-up gemaakt: %s (%.1f MB) in %.1fs%s",
        destination.name,
        size / (1024 * 1024),
        elapsed,
        f"; {len(removed)} oude verwijderd" if removed else "",
    )

    db = SessionLocal()
    try:
        audit.record(
            db,
            "backup.scheduled",
            f"Back-up gemaakt ({reason}): {destination.name},"
            f" {round(size / (1024 * 1024), 1)} MB"
            + (f" — {len(removed)} oude opgeruimd" if removed else ""),
            user_name="systeem",
        )
    finally:
        db.close()

    return BackupFile(
        name=destination.name,
        size=size,
        created_at=datetime.fromtimestamp(destination.stat().st_mtime).astimezone(),
    )


async def _loop(hour: int, minute: int) -> None:
    log.info(
        "Automatische back-ups staan aan: elke dag om %02d:%02d (tijdzone van de"
        " container), %d stuks bewaard in %s",
        hour,
        minute,
        settings.backup_keep,
        backups_dir(),
    )
    while True:
        delay = seconds_until(hour, minute)
        log.debug("Volgende back-up over %.0f minuten", delay / 60)
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(run_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never let one bad night end the schedule. A scheduler that has
            # quietly stopped is worse than none, because it looks fine.
            log.exception(
                "De automatische back-up is mislukt. De volgende poging is"
                " morgen om %02d:%02d.",
                hour,
                minute,
            )
        else:
            continue


def start(loop_factory=_loop) -> asyncio.Task | None:
    """Start the schedule, or return None when it is switched off."""
    parsed = parse_time(settings.backup_time)
    if parsed is None:
        if settings.backup_time.strip():
            return None  # parse_time already said why
        log.info(
            "Automatische back-ups staan uit (zet WARDROBE_BACKUP_TIME op bv. 03:30)."
        )
        return None
    hour, minute = parsed
    return asyncio.create_task(loop_factory(hour, minute), name="kledingkast-backup")
