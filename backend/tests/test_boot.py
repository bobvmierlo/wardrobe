"""What happens when the container starts.

The migrations used to run on every boot, which made "does this run twice
safely?" the only question worth asking. Now they run once, so there are two
more: does the version marker actually stop them, and is everything a fresh
database needs still there when they are skipped?

That second question is not hypothetical. Moving the bootstrap beheerder after
the migrations meant it no longer got a kast, because ``migrate_wardrobes`` had
already been and gone — a dependency on ordering that nothing stated. It was
caught by an unrelated test about deleting accounts, which is luck. So it has a
test of its own here.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app import migrations
from app.config import settings

BACKEND = Path(__file__).resolve().parent.parent


def boot(data_dir: Path, **env_extra: str) -> subprocess.CompletedProcess:
    """Start the app in a subprocess against ``data_dir`` and return its output."""
    env = {
        **os.environ,
        "WARDROBE_DATA_DIR": str(data_dir),
        "WARDROBE_SECRET_KEY": "test-secret-key-long-enough-for-hs256",
        "WARDROBE_LOG_LEVEL": "INFO",
        **env_extra,
    }
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def query(data_dir: Path, sql: str) -> list:
    con = sqlite3.connect(data_dir / "wardrobe.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# the step list itself
# ---------------------------------------------------------------------------

def test_the_steps_are_numbered_once_each_and_in_order():
    """A guard against the two ways appending a step goes wrong."""
    versions = [version for version, _name, _fn in migrations.STEPS]
    assert versions == sorted(versions), "steps must be in ascending order"
    assert len(versions) == len(set(versions)), "two steps share a version number"
    assert versions[0] == 1
    assert versions == list(range(1, len(versions) + 1)), "no gaps in the numbering"
    assert migrations.SCHEMA_VERSION == versions[-1]


def test_every_step_is_callable_and_named():
    for version, name, step in migrations.STEPS:
        assert isinstance(name, str) and name, version
        assert callable(step), name


# ---------------------------------------------------------------------------
# a fresh database
# ---------------------------------------------------------------------------

def test_a_fresh_database_boots_and_records_its_version(tmp_path):
    result = boot(tmp_path)
    assert result.returncode == 0, result.stderr
    assert query(tmp_path, "SELECT version FROM schema_version") == [
        (migrations.SCHEMA_VERSION,)
    ]


def test_the_bootstrap_beheerder_gets_a_kast(tmp_path):
    """The invariant that broke when the beheerder moved after the migrations.

    Every other way an account comes into being gives it a kast. This one used
    to get theirs from migrate_wardrobes, which only worked while that ran
    afterwards.
    """
    result = boot(tmp_path)
    assert result.returncode == 0, result.stderr

    admins = query(tmp_path, "SELECT id, username FROM users WHERE is_admin = 1")
    assert len(admins) == 1, admins
    admin_id, _username = admins[0]
    assert query(
        tmp_path, f"SELECT COUNT(*) FROM wardrobes WHERE owner_id = {admin_id}"
    ) == [(1,)]


def test_a_fresh_database_gets_the_catalogue_and_the_colour_rules(tmp_path):
    assert boot(tmp_path).returncode == 0
    assert query(tmp_path, "SELECT COUNT(*) FROM categories")[0][0] > 20
    assert query(tmp_path, "SELECT COUNT(*) FROM sizes")[0][0] > 15
    assert query(tmp_path, "SELECT COUNT(*) FROM color_rules")[0][0] > 0


# ---------------------------------------------------------------------------
# the second boot
# ---------------------------------------------------------------------------

def test_the_second_boot_skips_the_migrations(tmp_path):
    """The whole point: the repair sweep stops reading the database every start."""
    first = boot(tmp_path)
    assert first.returncode == 0, first.stderr
    assert "alle" in first.stdout and "stappen" in first.stdout

    second = boot(tmp_path)
    assert second.returncode == 0, second.stderr
    assert "geen migraties nodig" in second.stdout
    # None of the steps announced themselves, so none of them ran.
    assert "Migratie 1/" not in second.stdout
    for _version, name, _fn in migrations.STEPS:
        assert f": {name}" not in second.stdout, name


def test_the_second_boot_still_tops_up_a_newly_added_default(tmp_path):
    """Seeds run every boot on purpose; that is how a new size reaches an
    installation that already has a catalogue."""
    assert boot(tmp_path).returncode == 0
    con = sqlite3.connect(tmp_path / "wardrobe.db")
    con.execute("DELETE FROM sizes WHERE label = 'One-size'")
    con.commit()
    con.close()

    assert boot(tmp_path).returncode == 0
    assert query(tmp_path, "SELECT COUNT(*) FROM sizes WHERE label = 'One-size'") == [(1,)]


def test_the_repair_sweep_can_be_asked_for_again(tmp_path):
    """After restoring a backup by hand, "check for orphans" is a fair thing to want."""
    assert boot(tmp_path).returncode == 0
    quiet = boot(tmp_path)
    assert "opruimcontrole" not in quiet.stdout.lower() or "Databasecontrole" not in quiet.stdout

    asked = boot(tmp_path, WARDROBE_REPAIR_ON_START="true")
    assert asked.returncode == 0, asked.stderr
    assert "REPAIR_ON_START" in asked.stdout
    # The sweep says out loud that it found nothing, which is the whole reason
    # it says anything at all.
    assert "Databasecontrole" in asked.stdout


def test_an_interrupted_upgrade_keeps_the_steps_that_did_finish(tmp_path, monkeypatch):
    """Each step records itself, so a failure does not replay the ones before it."""
    assert boot(tmp_path).returncode == 0
    con = sqlite3.connect(tmp_path / "wardrobe.db")
    con.execute("UPDATE schema_version SET version = 4")
    con.commit()
    con.close()

    result = boot(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "schemaversie 4" in result.stdout
    # Only the steps after 4 announce themselves.
    assert "Migratie 5/" in result.stdout
    assert "Migratie 4/" not in result.stdout
    assert query(tmp_path, "SELECT version FROM schema_version") == [
        (migrations.SCHEMA_VERSION,)
    ]


# ---------------------------------------------------------------------------
# the pragmas and the indexes
# ---------------------------------------------------------------------------

def test_the_database_runs_in_wal_mode(tmp_path):
    """So a long export does not block the person swiping on their phone."""
    assert boot(tmp_path).returncode == 0
    assert query(tmp_path, "PRAGMA journal_mode")[0][0].lower() == "wal"


def test_foreign_keys_are_still_enforced(client):
    """WAL was added next to this; neither may quietly replace the other."""
    from app.database import engine

    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_photo_filenames_are_indexed(tmp_path):
    """Serving one photo should not read the whole items table."""
    assert boot(tmp_path).returncode == 0
    indexed = {
        row[0]
        for row in query(
            tmp_path,
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='items'",
        )
    }
    assert any("photo_filename" in name for name in indexed), indexed
    assert any("thumb_filename" in name for name in indexed), indexed


def test_the_index_is_actually_used_for_a_photo_lookup(tmp_path):
    """Asking SQLite rather than assuming: the index exists *and* the planner takes it."""
    assert boot(tmp_path).returncode == 0
    con = sqlite3.connect(tmp_path / "wardrobe.db")
    try:
        plan = con.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM items"
            " WHERE photo_filename = 'x.jpg' OR thumb_filename = 'x.jpg'"
        ).fetchall()
    finally:
        con.close()
    text = " ".join(str(row) for row in plan)
    assert "SCAN" not in text.upper() or "INDEX" in text.upper(), text


# ---------------------------------------------------------------------------
# the health endpoint
# ---------------------------------------------------------------------------

def test_health_reports_what_it_checked(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "uploads": "ok"}
    assert body["version"]


def test_health_answers_503_when_the_photos_cannot_be_written(client, monkeypatch, tmp_path):
    """A health check that cannot fail is decoration."""
    # uploads_dir is derived from data_dir, so that is the one to move. The
    # engine is already bound to the real database file, so only the photo
    # check breaks — which is what this is testing.
    monkeypatch.setattr(settings, "data_dir", tmp_path / "does-not-exist")
    response = client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["uploads"] == "niet beschrijfbaar"
    assert body["checks"]["database"] == "ok"


def test_health_answers_503_when_the_database_is_unreachable(client, monkeypatch):
    from app import main as main_module

    class Broken:
        def connect(self):
            raise RuntimeError("database is weg")

    monkeypatch.setattr(main_module, "engine", Broken())
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "onbereikbaar"


def test_health_needs_no_login(client):
    """Docker has no token to offer."""
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200
