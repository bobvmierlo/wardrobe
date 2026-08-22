"""Startup migrations against an existing database.

The other tests always start from an empty data dir, where ``create_all`` builds
the full schema — so they never exercise an *upgrade*. These boot the app in a
subprocess (module-level migrations run on import) against databases shaped like
earlier releases, which is where a missing column or a wrong migration order
actually bites.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

OLD_USERS = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY, username VARCHAR(50) UNIQUE, display_name VARCHAR(100),
    hashed_password VARCHAR(255), is_admin BOOLEAN, created_at DATETIME
);
INSERT INTO users VALUES (1, 'admin', 'Beheerder', 'x', 1, '2024-01-01');
INSERT INTO users VALUES (2, 'partner', 'Partner', 'x', 0, '2024-01-01');
"""

# items as it looked before brands moved into their own table: a free-text column.
def old_items(with_wardrobe_id: bool) -> str:
    extra = ", wardrobe_id INTEGER" if with_wardrobe_id else ""
    values = ", 1" if with_wardrobe_id else ""
    return f"""
CREATE TABLE items (
    id INTEGER PRIMARY KEY, name VARCHAR(120), category VARCHAR(60), brand VARCHAR(120),
    color VARCHAR(60), size VARCHAR(40), season VARCHAR(120), notes TEXT,
    photo_filename VARCHAR(200), thumb_filename VARCHAR(200), is_favorite BOOLEAN,
    created_by_id INTEGER, created_at DATETIME{extra}
);
INSERT INTO items VALUES (1,'Trui','Trui','Nike',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01'{values});
INSERT INTO items VALUES (2,'Broek','Broek','NIKE',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01'{values});
INSERT INTO items VALUES (3,'Jas','Jas','Zara',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01'{values});
"""


WARDROBES = """
CREATE TABLE wardrobes (
    id INTEGER PRIMARY KEY, owner_id INTEGER UNIQUE, name VARCHAR(120), created_at DATETIME
);
INSERT INTO wardrobes VALUES (1, 2, 'Kast van Partner', '2024-01-01');
"""


def boot(tmp_path: Path, script: str) -> subprocess.CompletedProcess:
    """Create a legacy database, then import the app so migrations run."""
    con = sqlite3.connect(tmp_path / "wardrobe.db")
    con.executescript(script)
    con.commit()
    con.close()

    env = {
        **os.environ,
        "WARDROBE_DATA_DIR": str(tmp_path),
        "WARDROBE_SECRET_KEY": "test-secret-key-long-enough-for-hs256",
    }
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def rows(tmp_path: Path, sql: str) -> list:
    con = sqlite3.connect(tmp_path / "wardrobe.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_upgrade_from_release_with_wardrobes_but_no_brands(tmp_path):
    """The shape shipped before brands got their own table (v0.3.0)."""
    result = boot(tmp_path, OLD_USERS + WARDROBES + old_items(with_wardrobe_id=True))
    assert result.returncode == 0, result.stderr

    # Brand rows created, spelling variants folded onto the oldest spelling.
    assert rows(tmp_path, "SELECT name FROM brands ORDER BY name") == [("Nike",), ("Zara",)]
    nike, _ = rows(tmp_path, "SELECT id, name FROM brands WHERE name = 'Nike'")[0]
    assert rows(tmp_path, "SELECT brand_id FROM items ORDER BY id")[:2] == [(nike,), (nike,)]


def test_upgrade_from_release_without_wardrobes_or_brands(tmp_path):
    """An older database still predating per-user wardrobes."""
    result = boot(tmp_path, OLD_USERS + old_items(with_wardrobe_id=False))
    assert result.returncode == 0, result.stderr

    # Every garment landed in its creator's kast...
    owner = rows(tmp_path, "SELECT id FROM wardrobes WHERE owner_id = 2")[0][0]
    assert rows(tmp_path, "SELECT DISTINCT wardrobe_id FROM items") == [(owner,)]
    # ...and its brand moved into the table.
    assert rows(tmp_path, "SELECT COUNT(*) FROM items WHERE brand_id IS NOT NULL") == [(3,)]


def test_second_boot_is_a_no_op(tmp_path):
    """Migrations must be safe to run again on every container start."""
    assert boot(tmp_path, OLD_USERS + old_items(with_wardrobe_id=False)).returncode == 0
    before = rows(tmp_path, "SELECT id, name FROM brands ORDER BY id")

    env = {
        **os.environ,
        "WARDROBE_DATA_DIR": str(tmp_path),
        "WARDROBE_SECRET_KEY": "test-secret-key-long-enough-for-hs256",
    }
    again = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    assert again.returncode == 0, again.stderr
    assert rows(tmp_path, "SELECT id, name FROM brands ORDER BY id") == before


def test_upgrade_creates_the_new_tables(tmp_path):
    """Skips, invitations and the audit trail arrive on an existing install.

    These are new tables rather than new columns, so ``create_all`` handles
    them — but only if it runs, and only if nothing earlier in the startup
    sequence blows up on a database that predates them.
    """
    result = boot(tmp_path, OLD_USERS + WARDROBES + old_items(with_wardrobe_id=True))
    assert result.returncode == 0, result.stderr

    tables = {
        name for (name,) in rows(
            tmp_path, "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"match_skips", "invitations", "audit_logs"} <= tables
    # Empty, not backfilled: there is no history to invent for them.
    for table in ("match_skips", "invitations", "audit_logs"):
        assert rows(tmp_path, f"SELECT COUNT(*) FROM {table}") == [(0,)]


# A database as an earlier release left it after "deleting" user 2: the users
# row is gone, but their kast, garments, verdicts and invitation are still
# there, pointing at an account that no longer exists.
ORPHANED = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY, username VARCHAR(50) UNIQUE, display_name VARCHAR(100),
    hashed_password VARCHAR(255), is_admin BOOLEAN, created_at DATETIME
);
INSERT INTO users VALUES (1, 'admin', 'Beheerder', 'x', 1, '2024-01-01');

CREATE TABLE wardrobes (
    id INTEGER PRIMARY KEY, owner_id INTEGER UNIQUE, name VARCHAR(120), created_at DATETIME
);
INSERT INTO wardrobes VALUES (1, 1, 'Kast van Beheerder', '2024-01-01');
INSERT INTO wardrobes VALUES (2, 2, 'Kast van de verwijderde gebruiker', '2024-01-01');

CREATE TABLE items (
    id INTEGER PRIMARY KEY, name VARCHAR(120), category VARCHAR(60),
    color VARCHAR(60), size VARCHAR(40), season VARCHAR(120), notes TEXT,
    photo_filename VARCHAR(200), thumb_filename VARCHAR(200), is_favorite BOOLEAN,
    created_by_id INTEGER, created_at DATETIME, wardrobe_id INTEGER, brand_id INTEGER
);
-- Two garments in the orphaned kast...
INSERT INTO items VALUES (1,'Trui','Trui',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01',2,NULL);
INSERT INTO items VALUES (2,'Broek','Broek',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01',2,NULL);
-- ...and one they added to the admin's kast, which must be kept.
INSERT INTO items VALUES (3,'Jas','Jas',NULL,NULL,NULL,NULL,NULL,NULL,0,2,'2024-01-01',1,NULL);

CREATE TABLE matches (
    id INTEGER PRIMARY KEY, item_a_id INTEGER, item_b_id INTEGER, user_id INTEGER,
    verdict VARCHAR(3), created_at DATETIME, updated_at DATETIME
);
INSERT INTO matches VALUES (1, 1, 2, 2, 'yes', '2024-01-01', '2024-01-01');

CREATE TABLE wardrobe_members (
    id INTEGER PRIMARY KEY, wardrobe_id INTEGER, user_id INTEGER,
    role VARCHAR(10), created_at DATETIME
);
INSERT INTO wardrobe_members VALUES (1, 1, 2, 'editor', '2024-01-01');
"""


def test_upgrade_sweeps_up_after_a_half_finished_deletion(tmp_path):
    """An account deleted by an older release left its kast behind.

    That orphaned kast is not just clutter: SQLite hands the freed user id to
    the next account created, which would then open the app looking at the
    departed person's clothes. The upgrade has to clear it.
    """
    result = boot(tmp_path, ORPHANED)
    assert result.returncode == 0, result.stderr

    # The ownerless kast and everything in it is gone...
    assert rows(tmp_path, "SELECT COUNT(*) FROM wardrobes WHERE owner_id = 2") == [(0,)]
    assert rows(tmp_path, "SELECT COUNT(*) FROM items WHERE wardrobe_id = 2") == [(0,)]
    assert rows(tmp_path, "SELECT COUNT(*) FROM matches") == [(0,)]
    assert rows(tmp_path, "SELECT COUNT(*) FROM wardrobe_members WHERE user_id = 2") == [(0,)]

    # ...but the garment in the admin's kast survives, re-homed to the admin.
    assert rows(tmp_path, "SELECT name, wardrobe_id, created_by_id FROM items") == [
        ("Jas", 1, 1)
    ]
    # The admin's own kast is untouched.
    assert rows(tmp_path, "SELECT COUNT(*) FROM wardrobes WHERE owner_id = 1") == [(1,)]


def test_the_orphan_sweep_is_safe_to_run_again(tmp_path):
    assert boot(tmp_path, ORPHANED).returncode == 0
    before = rows(tmp_path, "SELECT id, name, wardrobe_id FROM items ORDER BY id")
    wardrobes_before = rows(tmp_path, "SELECT id, owner_id FROM wardrobes ORDER BY id")

    env = {
        **os.environ,
        "WARDROBE_DATA_DIR": str(tmp_path),
        "WARDROBE_SECRET_KEY": "test-secret-key-long-enough-for-hs256",
    }
    again = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    assert again.returncode == 0, again.stderr
    assert rows(tmp_path, "SELECT id, name, wardrobe_id FROM items ORDER BY id") == before
    assert rows(tmp_path, "SELECT id, owner_id FROM wardrobes ORDER BY id") == wardrobes_before


def test_a_healthy_database_is_left_completely_alone(tmp_path):
    """The sweep must never touch data that is fine."""
    result = boot(tmp_path, OLD_USERS + WARDROBES + old_items(with_wardrobe_id=True))
    assert result.returncode == 0, result.stderr
    # Both users still there, all three garments still in the partner's kast.
    assert rows(tmp_path, "SELECT COUNT(*) FROM users") == [(2,)]
    assert rows(tmp_path, "SELECT COUNT(*) FROM items") == [(3,)]
    assert rows(tmp_path, "SELECT COUNT(*) FROM wardrobes WHERE owner_id = 2") == [(1,)]
