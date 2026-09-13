"""Backups that happen without anyone remembering.

The point of this feature is that it is unattended, which means every failure
mode is a silent one. So the tests lean on the things that would otherwise only
be discovered by needing a backup and not having one: that the schedule
survives a bad night, that rotation never eats a file it did not write, and that
a name arriving from a URL cannot address anything outside the folder.
"""

import asyncio
import pathlib
import zipfile
from datetime import datetime, timedelta

import pytest

from app import scheduled_backup as sb
from app.config import settings


class _Stop(BaseException):
    """Breaks out of the endless loop without being caught as a failure.

    A BaseException on purpose: the loop swallows every ``Exception`` by design,
    which is exactly what these tests are checking, so the escape hatch has to
    be something it does not catch.
    """


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_token(client) -> str:
    from app.throttle import login_throttle

    login_throttle.reset()
    return client.post(
        "/api/auth/login", data={"username": "admin", "password": "changeme"}
    ).json()["access_token"]


@pytest.fixture(autouse=True)
def clean_backups_dir():
    """Start and finish with an empty backup folder."""
    def wipe():
        for path in sb.backups_dir().iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
    wipe()
    yield
    wipe()


# ---------------------------------------------------------------------------
# reading the schedule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [("03:30", (3, 30)), ("0:0", (0, 0)), ("23:59", (23, 59)), (" 4:05 ", (4, 5))],
)
def test_a_time_of_day_is_understood(value, expected):
    assert sb.parse_time(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "bogus", "25:00", "03:60", "-1:00", "03", "03:xx"])
def test_anything_else_switches_the_schedule_off(value):
    """Rather than guessing. An unparseable time is said out loud in the log."""
    assert sb.parse_time(value) is None


def test_the_wait_is_until_the_next_time_it_is_that_hour():
    now = datetime(2026, 9, 12, 22, 0, 0)
    assert sb.seconds_until(23, 0, now=now) == 3600
    # Already past today, so tomorrow.
    assert sb.seconds_until(3, 30, now=now) == 5.5 * 3600


def test_exactly_now_means_tomorrow_rather_than_immediately():
    """Otherwise a restart at 03:30 would back up on every restart."""
    now = datetime(2026, 9, 12, 3, 30, 0)
    assert sb.seconds_until(3, 30, now=now) == 24 * 3600


def test_the_wait_is_never_negative():
    now = datetime(2026, 9, 12, 23, 59, 59)
    assert sb.seconds_until(0, 0, now=now) > 0


# ---------------------------------------------------------------------------
# writing one
# ---------------------------------------------------------------------------

def test_a_backup_is_a_zip_with_the_database_and_the_photos_in_it(client):
    file = sb.run_once()
    assert file.name.startswith(sb.PREFIX)
    assert file.name.endswith(".zip")

    path = sb.backups_dir() / file.name
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    # A snapshot, not an export: the database itself, which is what makes it
    # restorable by copying rather than by walking the data back in.
    assert any(name.endswith("wardrobe.db") for name in names), names


def test_the_backup_shows_up_in_the_listing(client):
    sb.run_once()
    listed = sb.list_backups()
    assert len(listed) == 1
    assert listed[0].size > 0
    # size_mb is what the log line prints; it has to track the real size rather
    # than just being non-negative, which was all the old assertion checked.
    assert listed[0].size_mb == round(listed[0].size / (1024 * 1024), 1)


def test_it_is_recorded_in_the_audit_trail(client):
    sb.run_once(reason="voor de test")
    trail = client.get(
        "/api/audit", headers=h(admin_token(client)), params={"action": "backup.scheduled"}
    ).json()
    assert trail["total"] >= 1
    assert "voor de test" in trail["entries"][0]["detail"]


def test_a_failed_copy_leaves_nothing_that_looks_like_a_backup(client, monkeypatch):
    """A truncated zip under a normal name is worse than no backup at all.

    It looks like one. So the bytes land under a name the listing ignores and
    only get the real name once they are all there.
    """
    def full_disk(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sb.shutil, "move", full_disk)
    with pytest.raises(OSError):
        sb.run_once()

    assert sb.list_backups() == []
    leftovers = list(sb.backups_dir().iterdir())
    assert leftovers == [], leftovers


def test_a_failure_between_copy_and_rename_keeps_yesterdays_backup(client, monkeypatch):
    """The destination may well be a perfectly good older backup."""
    _fake_backup(f"{sb.PREFIX}gisteren.zip", age_days=1)

    def failing_rename(self, _target):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(pathlib.Path, "replace", failing_rename)
    with pytest.raises(OSError):
        sb.run_once()

    # Yesterday's is still there, and no half-written file joined it.
    assert [f.name for f in sb.list_backups()] == [f"{sb.PREFIX}gisteren.zip"]
    assert not any(p.name.endswith(".incomplete") for p in sb.backups_dir().iterdir())


def test_two_backups_in_the_same_second_do_not_overwrite_each_other(client):
    """One double-click on "nu maken" is all it takes."""
    moment = datetime(2026, 9, 13, 3, 30, 0)
    first = sb._free_destination(moment)
    first.write_bytes(b"de eerste")
    second = sb._free_destination(moment)
    assert second != first
    assert second.name.startswith(sb.PREFIX)
    second.write_bytes(b"de tweede")
    assert first.read_bytes() == b"de eerste"
    assert len(sb.list_backups()) == 2


# ---------------------------------------------------------------------------
# throwing the old ones away
# ---------------------------------------------------------------------------

def _fake_backup(name: str, *, age_days: float = 0) -> None:
    path = sb.backups_dir() / name
    path.write_bytes(b"niet echt een zip")
    stamp = (datetime.now() - timedelta(days=age_days)).timestamp()
    import os

    os.utime(path, (stamp, stamp))


def test_rotation_keeps_the_newest_and_drops_the_rest():
    for day in range(5):
        _fake_backup(f"{sb.PREFIX}dag{day}.zip", age_days=day)
    removed = sb.rotate(keep=2)
    assert len(removed) == 3
    kept = [f.name for f in sb.list_backups()]
    assert kept == [f"{sb.PREFIX}dag0.zip", f"{sb.PREFIX}dag1.zip"]


def test_rotation_never_touches_a_file_it_did_not_write():
    """Somebody's own copy in that folder is theirs, not ours to tidy up.

    Deliberately the *oldest* file in the folder: a rotation that forgot to look
    at the prefix sorts by age and would reach this one first. Written newest,
    this test passed even with that bug — found by mutating the prefix filter
    away and watching nothing fail.
    """
    mine = sb.backups_dir() / "mijn-eigen-backup.zip"
    mine.write_bytes(b"van mij")
    import os
    ancient = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(mine, (ancient, ancient))

    for day in range(3):
        _fake_backup(f"{sb.PREFIX}d{day}.zip", age_days=day)

    sb.rotate(keep=1)
    assert mine.exists(), "rotation deleted a file it did not write"
    assert len(sb.list_backups()) == 1


def test_keeping_zero_still_keeps_one():
    """A misconfigured 0 must not mean "delete the backup you just made"."""
    for day in range(3):
        _fake_backup(f"{sb.PREFIX}d{day}.zip", age_days=day)
    sb.rotate(keep=0)
    assert len(sb.list_backups()) == 1


def test_rotation_happens_as_part_of_making_one(client, monkeypatch):
    monkeypatch.setattr(settings, "backup_keep", 2)
    for day in range(1, 4):
        _fake_backup(f"{sb.PREFIX}oud{day}.zip", age_days=day)
    sb.run_once()
    assert len(sb.list_backups()) == 2


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------

def test_the_schedule_survives_a_backup_that_fails(monkeypatch):
    """A full disk tonight must not mean no backups ever again.

    A scheduler that has quietly stopped is worse than no scheduler, because it
    looks like it is working.
    """
    attempts: list[int] = []

    def failing() -> None:
        attempts.append(1)
        if len(attempts) >= 3:
            raise _Stop
        raise RuntimeError("schijf vol")

    monkeypatch.setattr(sb, "run_once", failing)
    monkeypatch.setattr(sb, "seconds_until", lambda *_a, **_k: 0)

    async def drive():
        with pytest.raises(_Stop):
            await sb._loop(3, 30)

    asyncio.run(drive())
    # Two failures did not stop it; it came back for a third night.
    assert len(attempts) == 3


def test_the_loop_keeps_going_after_a_successful_run(monkeypatch):
    runs: list[int] = []

    def succeeding():
        runs.append(1)
        if len(runs) >= 2:
            raise _Stop
        return sb.BackupFile(name="auto-x.zip", size=1, created_at=datetime.now())

    monkeypatch.setattr(sb, "run_once", succeeding)
    monkeypatch.setattr(sb, "seconds_until", lambda *_a, **_k: 0)

    async def drive():
        with pytest.raises(_Stop):
            await sb._loop(3, 30)

    asyncio.run(drive())
    assert len(runs) == 2


def test_start_does_nothing_when_there_is_no_schedule(monkeypatch):
    monkeypatch.setattr(settings, "backup_time", "")

    async def drive():
        assert sb.start() is None

    asyncio.run(drive())


def test_start_does_nothing_when_the_schedule_is_nonsense(monkeypatch):
    monkeypatch.setattr(settings, "backup_time", "elke dinsdag")

    async def drive():
        assert sb.start() is None

    asyncio.run(drive())


def test_start_schedules_the_time_it_was_given(monkeypatch):
    monkeypatch.setattr(settings, "backup_time", "04:15")
    seen: list[tuple[int, int]] = []

    async def fake_loop(hour: int, minute: int) -> None:
        seen.append((hour, minute))

    async def drive():
        task = sb.start(loop_factory=fake_loop)
        assert task is not None
        await task

    asyncio.run(drive())
    assert seen == [(4, 15)]


# ---------------------------------------------------------------------------
# reaching them over HTTP
# ---------------------------------------------------------------------------

def test_only_a_beheerder_sees_the_backups(client):
    from tests.test_hardening import make_user

    _username, token = make_user(client)
    assert client.get("/api/backup/scheduled", headers=h(token)).status_code == 403
    assert client.get("/api/backup/scheduled").status_code == 401


def test_the_listing_says_what_the_schedule_is(client, monkeypatch):
    monkeypatch.setattr(settings, "backup_time", "03:30")
    monkeypatch.setattr(settings, "backup_keep", 5)
    body = client.get("/api/backup/scheduled", headers=h(admin_token(client))).json()
    assert body == {"time": "03:30", "keep": 5, "enabled": True, "backups": []}


def test_the_listing_admits_when_the_schedule_is_unusable(client, monkeypatch):
    monkeypatch.setattr(settings, "backup_time", "halverwege de nacht")
    body = client.get("/api/backup/scheduled", headers=h(admin_token(client))).json()
    assert body["enabled"] is False
    assert body["time"] == "halverwege de nacht"


def test_a_beheerder_can_make_one_now(client):
    token = admin_token(client)
    created = client.post("/api/backup/scheduled/run", headers=h(token))
    assert created.status_code == 201, created.text
    body = created.json()
    name = body["name"]
    assert name.startswith(sb.PREFIX)
    # Bytes, not a rounded megabyte: a fresh kast backs up to a few kB and
    # "0.0 MB" would read as "nothing was saved".
    assert body["size_bytes"] > 0
    assert body["size_bytes"] == (sb.backups_dir() / name).stat().st_size

    listed = client.get("/api/backup/scheduled", headers=h(token)).json()
    assert [b["name"] for b in listed["backups"]] == [name]


def test_a_beheerder_can_download_one(client):
    token = admin_token(client)
    name = client.post("/api/backup/scheduled/run", headers=h(token)).json()["name"]
    response = client.get(f"/api/backup/scheduled/{name}", headers=h(token))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert len(response.content) > 0
    # Downloading must not consume it — unlike the temporary exports, this file
    # *is* the backup.
    assert sb.resolve(name) is not None


def test_an_unknown_backup_is_a_404(client):
    response = client.get("/api/backup/scheduled/auto-bestaat-niet.zip", headers=h(admin_token(client)))
    assert response.status_code == 404


@pytest.mark.parametrize(
    "name",
    ["../wardrobe.db", "../../etc/passwd", "wardrobe.db", "auto-../../wardrobe.db", ""],
)
def test_a_name_cannot_reach_outside_the_backup_folder(name):
    """The name comes from a URL, so it is matched against what is actually in
    the folder rather than joined onto a path."""
    assert sb.resolve(name) is None


def test_a_file_in_the_folder_that_is_not_ours_is_not_handed_over():
    """What the prefix check is actually for.

    The traversal cases above return None because no such file exists, which
    would be just as true without any check at all — mutating the prefix guard
    away broke nothing. This is the case that needs it: a real, readable file
    sitting in the folder that the app did not write.
    """
    mine = sb.backups_dir() / "mijn-eigen-backup.zip"
    mine.write_bytes(b"van mij")
    assert mine.exists()
    assert sb.resolve("mijn-eigen-backup.zip") is None
