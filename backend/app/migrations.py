"""Bringing the database up to date, once.

This used to live in :mod:`app.main`, 450 of its 713 lines, executing as a side
effect of importing the module. That had three costs: a failure was a crash loop
with a traceback instead of a diagnosis, ``uvicorn --reload`` re-ran the lot on
every code change, and importing the app to run a test meant migrating a
database.

It also ran *everything* on every single boot. Most of the steps are cheap
no-ops once applied — they check ``PRAGMA table_info`` and return — but
:func:`migrate_orphans` is a data repair that reads ``items``, ``matches`` and
``match_skips`` into Python in their entirety. At two hundred garments that is
free. It does not stay free.

So there are now two kinds of startup work, and they are treated differently:

**Migrations** are numbered and run once. A ``schema_version`` row records how
far this database has come; steps at or below it are skipped entirely. Every
step is still written to be idempotent — an existing installation starts at
version 0 with all of them already applied, so they all have to be safe to meet
again exactly once — but after that first boot they are not even called.

**Seeds** run every boot, on purpose. :func:`seed_catalog` does not only fill an
empty database; it tops up defaults added in a later release, which is how a new
shoe size reaches an installation that already has a catalogue. Gating that
behind a version number would mean remembering to bump the number every time the
default lists change, and forgetting would be silent. They cost two counting
queries, so they simply run.

The repair sweep is a migration — once — with ``WARDROBE_REPAIR_ON_START=true``
to ask for it again, because "run the orphan check" is a reasonable thing to want
after restoring a backup by hand.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .accounts import purge_wardrobe
from .access import ensure_wardrobe
from .config import settings
from .database import Base, SessionLocal, engine
from .images import delete_files
from .logging_setup import get_logger
from .models import (
    AuditLog,
    Category,
    ColorRule,
    Invitation,
    Item,
    Match,
    MatchSkip,
    OccasionOption,
    SizeOption,
    User,
    Wardrobe,
    WardrobeMember,
)
from .security import hash_password
from .suggestions import DEFAULT_BAD_PAIRS, DEFAULT_GOOD_PAIRS
from .tags import DEFAULT_OCCASIONS

log = get_logger("migrations")

DEFAULT_CATEGORIES = [
    "Polo", "T-shirt", "Overhemd", "Blouse", "Trui", "Vest", "Hoodie",
    "Sweater", "Broek", "Jeans", "Chino", "Shorts", "Rok", "Jurk", "Jas",
    "Blazer", "Bodywarmer", "Schoenen", "Sneakers", "Laarzen", "Riem",
    "Sjaal", "Muts", "Pet", "Das", "Tas",
]
# (label, kind) pairs. "clothing" = confectiematen, "shoes" = EU-schoenmaten,
# "accessory" = one-size voor mutsen/sjaals e.d.
DEFAULT_SIZES: list[tuple[str, str]] = [
    *[(s, "clothing") for s in ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]],
    *[(str(n), "shoes") for n in range(36, 48)],
    ("One-size", "accessory"),
]



def seed_admin() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username=settings.admin_username.strip().lower(),
                    display_name=settings.admin_display_name,
                    hashed_password=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )
            db.commit()
            # Give it a kast straight away, like every other way an account is
            # created does (see access.ensure_wardrobe's callers). Leaving this
            # to migrate_wardrobes worked only for as long as that happened to
            # run afterwards — a dependency on ordering that nothing stated and
            # that broke the moment the ordering changed.
            admin = db.query(User).filter(
                User.username == settings.admin_username.strip().lower()
            ).first()
            if admin is not None:
                ensure_wardrobe(db, admin)
            log.warning(
                "Beheerder aangemaakt: '%s'. Wijzig het wachtwoord na de eerste login.",
                settings.admin_username,
            )
    finally:
        db.close()


def migrate_sizes() -> None:
    """Add the sizes.kind column if an earlier build created the table without it."""
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(sizes)").fetchall()
        if rows and not any(r[1] == "kind" for r in rows):
            conn.exec_driver_sql(
                "ALTER TABLE sizes ADD COLUMN kind VARCHAR(20) DEFAULT 'clothing'"
            )


def migrate_size_uniqueness() -> None:
    """Rebuild the sizes table so labels are unique per kind instead of globally.

    Early builds made ``label`` globally unique, which blocked adding a clothing
    size like "40"/"42" when the same number already existed as a shoe size.
    SQLite can't drop a constraint in place, so detect the old single-column
    unique index and rebuild the table with a composite (label, kind) unique.
    """
    with engine.begin() as conn:
        tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sizes'"
        ).fetchall()
        if not tables:
            return  # fresh install: create_all already made the correct schema
        needs_rebuild = False
        for idx in conn.exec_driver_sql("PRAGMA index_list(sizes)").fetchall():
            name, unique = idx[1], idx[2]
            if not unique:
                continue
            cols = [c[2] for c in conn.exec_driver_sql(f"PRAGMA index_info('{name}')").fetchall()]
            if cols == ["label"]:  # the old global-unique index
                needs_rebuild = True
                break
        if not needs_rebuild:
            return
        conn.exec_driver_sql(
            "CREATE TABLE sizes_new ("
            " id INTEGER PRIMARY KEY,"
            " label VARCHAR(40) NOT NULL,"
            " kind VARCHAR(20) DEFAULT 'clothing',"
            " position INTEGER DEFAULT 0,"
            " CONSTRAINT uq_sizes_label_kind UNIQUE (label, kind))"
        )
        conn.exec_driver_sql(
            "INSERT INTO sizes_new (id, label, kind, position)"
            " SELECT id, label, kind, position FROM sizes"
        )
        conn.exec_driver_sql("DROP TABLE sizes")
        conn.exec_driver_sql("ALTER TABLE sizes_new RENAME TO sizes")


def _add_item_tag_columns(conn) -> None:
    """Add ``items.occasion``/``weather``/``style`` when they are missing.

    Called from two steps on purpose. A database at version 0 has to get these
    in :func:`migrate_schema`, because the steps after it query ``items``
    through the ORM and a mapped column the database lacks makes *every* one of
    those queries fail. A database that already passed that step never runs it
    again, so :func:`migrate_outfits_and_tags` adds them there instead. Both
    check first, so whichever runs second does nothing.
    """
    cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(items)").fetchall()]
    if not cols:
        return  # fresh install: create_all already made the full schema
    for column in ("occasion", "weather", "style"):
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE items ADD COLUMN {column} VARCHAR(200)")


def migrate_schema() -> None:
    """Create new tables and add columns an older database is missing.

    Must run before any migration that uses the ORM. A mapped column that does
    not exist yet makes *every* ORM query on that table fail — which is exactly
    what broke startup when items gained ``brand_id`` while migrate_wardrobes()
    still ran first: ``create_all`` adds missing tables, never missing columns.
    """
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(items)").fetchall()]
        if not cols:
            return  # fresh install: create_all already made the full schema
        if "wardrobe_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE items ADD COLUMN wardrobe_id INTEGER REFERENCES wardrobes(id)"
            )
        if "brand_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE items ADD COLUMN brand_id INTEGER REFERENCES brands(id)"
            )
        if "uid" not in cols:
            # Backups reference garments by uid, so every existing row needs
            # one before the first export can run: add the column, fill it,
            # and only then index it.
            conn.exec_driver_sql("ALTER TABLE items ADD COLUMN uid VARCHAR(32)")
            for (item_id,) in conn.exec_driver_sql("SELECT id FROM items").fetchall():
                conn.exec_driver_sql(
                    "UPDATE items SET uid = ? WHERE id = ?", (uuid.uuid4().hex, item_id)
                )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_items_uid ON items (uid)")
        # Unique per kast, not globally: create_all cannot add a constraint to
        # a table that already exists, so an index does the same job here.
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_item_wardrobe_uid ON items (wardrobe_id, uid)"
        )
        # Must happen here rather than only in the step that introduced them:
        # every step below this one reads ``items`` through the ORM.
        _add_item_tag_columns(conn)


def migrate_outfits_and_tags() -> None:
    """Add the tables and columns that outfits, the planner and the weather need.

    ``create_all`` makes every new *table* (outfits, wear logs, trips, per-user
    preferences); only the three new tag columns on ``items`` need adding by
    hand, because it never touches a table that already exists.
    """
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _add_item_tag_columns(conn)
        # Same reasoning as items: a constraint cannot be added to an existing
        # table, and a unique index does the same job.
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_outfit_wardrobe_uid"
            " ON outfits (wardrobe_id, uid)"
        )


def migrate_token_versions() -> None:
    """Add ``users.token_version`` so tokens become revocable.

    Everyone starts at 1, which is also what a token without the claim counts
    as — so nobody is signed out by the upgrade itself, and the first password
    change after it is what actually retires the old tokens.
    """
    with engine.begin() as conn:
        cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if not cols:
            return  # fresh install: create_all already made the full schema
        if "token_version" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1"
            )
            conn.exec_driver_sql(
                "UPDATE users SET token_version = 1 WHERE token_version IS NULL"
            )


def migrate_federated_login() -> None:
    """Add the columns a federated login needs on an existing database.

    ``hashed_password`` stays NOT NULL: an account without a local password
    stores an unusable sentinel instead (see :mod:`app.security`), which saves
    rebuilding the one table every other row in the database points at.
    """
    with engine.begin() as conn:
        cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if not cols:
            return  # fresh install: create_all already made the full schema
        if "auth_provider" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local'"
            )
        if "oidc_subject" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN oidc_subject VARCHAR(255)")
        # Two accounts must never share one provider identity. Unique rather
        # than plain: SQLite treats NULLs as distinct, so every local account
        # (which has none) still fits.
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_oidc_subject"
            " ON users (oidc_subject)"
        )


def migrate_account_invitations() -> None:
    """Let ``invitations.wardrobe_id`` be NULL, for account invitations.

    Every invitation used to belong to a kast, so the column was NOT NULL. An
    account invitation belongs to no kast at all, and SQLite cannot relax a
    constraint in place — so rebuild the table once, keeping every existing
    link exactly as it was.
    """
    with engine.begin() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(invitations)").fetchall()
        if not cols:
            return  # fresh install: create_all already made the correct schema
        # (cid, name, type, notnull, default, pk)
        if not any(c[1] == "wardrobe_id" and c[3] for c in cols):
            return  # already nullable

        # Links pointing at a kast or a creator that is gone would fail the
        # copy (foreign keys are enforced). They are wreckage either way —
        # migrate_orphans would drop them minutes later — so drop them here.
        conn.exec_driver_sql(
            "DELETE FROM invitations WHERE wardrobe_id NOT IN (SELECT id FROM wardrobes)"
            " OR created_by_id NOT IN (SELECT id FROM users)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE invitations_new ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " token VARCHAR(64) NOT NULL,"
            " wardrobe_id INTEGER REFERENCES wardrobes(id) ON DELETE CASCADE,"
            " role VARCHAR(10),"
            " label VARCHAR(120),"
            " created_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
            " created_at DATETIME,"
            " expires_at DATETIME,"
            " accepted_at DATETIME,"
            " accepted_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
            " revoked_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO invitations_new (id, token, wardrobe_id, role, label,"
            " created_by_id, created_at, expires_at, accepted_at, accepted_by_id,"
            " revoked_at)"
            " SELECT id, token, wardrobe_id, role, label, created_by_id, created_at,"
            " expires_at, accepted_at, accepted_by_id, revoked_at FROM invitations"
        )
        conn.exec_driver_sql("DROP TABLE invitations")
        conn.exec_driver_sql("ALTER TABLE invitations_new RENAME TO invitations")
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_invitations_token ON invitations (token)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_invitations_wardrobe_id"
            " ON invitations (wardrobe_id)"
        )
        log.info("Uitnodigingen: kolom wardrobe_id mag nu leeg zijn (accountuitnodigingen)")


def migrate_wardrobes() -> None:
    """Give every user a wardrobe and move existing garments into one.

    Introduced when the app gained per-user wardrobes ("kasten") with sharing.
    On existing installs the ``items`` table predates the ``wardrobe_id``
    column, so add it, create one wardrobe per user, and file each garment
    under its creator's wardrobe (falling back to the first admin's).
    """
    db = SessionLocal()
    try:
        existing = {w.owner_id for w in db.query(Wardrobe).all()}
        for u in db.query(User).all():
            if u.id not in existing:
                db.add(Wardrobe(owner_id=u.id, name=f"Kast van {u.display_name}"))
        db.commit()

        owner_to_wardrobe = {w.owner_id: w.id for w in db.query(Wardrobe).all()}
        admin = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first()
        fallback = owner_to_wardrobe.get(admin.id) if admin else None

        orphans = db.query(Item).filter(Item.wardrobe_id.is_(None)).all()
        for it in orphans:
            it.wardrobe_id = owner_to_wardrobe.get(it.created_by_id) or fallback
        if orphans:
            db.commit()
    finally:
        db.close()


def migrate_brands() -> None:
    """Move free-text item brands into the shared ``brands`` table.

    Brands used to be a plain string column on ``items``, so the same brand
    could exist under several spellings. Create the table, add ``brand_id``,
    and fold each distinct name into one row case-insensitively, keeping the
    spelling of the oldest garment that used it. The old column is left in
    place (SQLite cannot drop one) but is no longer read.
    """
    with engine.begin() as conn:
        cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(items)").fetchall()]
        if "brand" not in cols:
            return  # fresh install, or already past the free-text brand column

        seen: dict[str, int] = {
            name.strip().lower(): brand_id
            for brand_id, name in conn.exec_driver_sql("SELECT id, name FROM brands").fetchall()
        }
        rows = conn.exec_driver_sql(
            "SELECT id, brand FROM items"
            " WHERE brand_id IS NULL AND brand IS NOT NULL AND TRIM(brand) <> ''"
            " ORDER BY id"
        ).fetchall()
        for item_id, brand in rows:
            name = (brand or "").strip()
            if not name:
                continue
            brand_id = seen.get(name.lower())
            if brand_id is None:
                cur = conn.exec_driver_sql(
                    "INSERT INTO brands (name, created_at) VALUES (?, ?)",
                    (name, datetime.now(timezone.utc)),
                )
                brand_id = cur.lastrowid
                seen[name.lower()] = brand_id
            conn.exec_driver_sql(
                "UPDATE items SET brand_id = ? WHERE id = ?", (brand_id, item_id)
            )


def migrate_orphans() -> None:
    """Clean up rows left behind by a deletion that never finished.

    Until this release, deleting a user removed one row and left their kast,
    garments, verdicts and invitations pointing at an account that no longer
    existed. That is bad on its own, and actively dangerous in SQLite: a freed
    row id gets handed to the next account created, which then inherits the
    departed person's wardrobe.

    So sweep the wreckage once, on startup. Anything still referencing a row
    that is gone is either re-homed (garments keep their kast, authorship moves
    to an admin) or removed (a kast whose owner no longer exists, and verdicts
    about garments that no longer exist).
    """
    db = SessionLocal()
    try:
        user_ids = {u.id for u in db.query(User).all()}
        if not user_ids:
            return  # nothing to anchor to; seed_admin runs before this
        admin = (
            db.query(User)
            .filter(User.is_admin.is_(True))
            .order_by(User.id)
            .first()
        )
        removed: dict[str, int] = {}

        # A kast whose owner is gone: nobody can reach it, and the next account
        # to be given that id would silently inherit it.
        stray = [w for w in db.query(Wardrobe).all() if w.owner_id not in user_ids]
        if stray:
            items = 0
            for wardrobe in stray:
                items += purge_wardrobe(db, wardrobe)
            db.commit()
            removed["kasten"] = len(stray)
            removed["kledingstukken"] = items
            user_ids = {u.id for u in db.query(User).all()}

        wardrobe_ids = {w.id for w in db.query(Wardrobe).all()}
        item_ids = {i.id for i in db.query(Item).all()}

        # Garments filed under a kast that no longer exists.
        lost_items = [
            i for i in db.query(Item).all()
            if i.wardrobe_id is not None and i.wardrobe_id not in wardrobe_ids
        ]
        for item in lost_items:
            delete_files(item.photo_filename, item.thumb_filename)
            db.delete(item)
        if lost_items:
            db.commit()
            removed["losse kledingstukken"] = len(lost_items)
            item_ids = {i.id for i in db.query(Item).all()}

        # Verdicts and postponements about garments or people that are gone.
        for model, label in ((Match, "beoordelingen"), (MatchSkip, "overslagen")):
            gone = [
                row for row in db.query(model).all()
                if row.user_id not in user_ids
                or row.item_a_id not in item_ids
                or row.item_b_id not in item_ids
            ]
            for row in gone:
                db.delete(row)
            if gone:
                removed[label] = len(gone)

        # Access grants and links pointing at somebody who left.
        dangling_members = [
            m for m in db.query(WardrobeMember).all()
            if m.user_id not in user_ids or m.wardrobe_id not in wardrobe_ids
        ]
        for member in dangling_members:
            db.delete(member)
        if dangling_members:
            removed["gedeelde toegangen"] = len(dangling_members)

        # An account invitation has no kast on purpose; only a link pointing at
        # a kast that is *gone* is wreckage.
        dangling_invites = [
            inv for inv in db.query(Invitation).all()
            if (inv.wardrobe_id is not None and inv.wardrobe_id not in wardrobe_ids)
            or inv.created_by_id not in user_ids
        ]
        for invitation in dangling_invites:
            db.delete(invitation)
        if dangling_invites:
            removed["uitnodigingen"] = len(dangling_invites)
        db.commit()

        # Keep the garment, move the authorship: an item added to a shared kast
        # outlives the person who added it.
        if admin is not None:
            reassigned = (
                db.query(Item)
                .filter(Item.created_by_id.notin_(user_ids))
                .update({Item.created_by_id: admin.id}, synchronize_session=False)
            )
            if reassigned:
                removed["kledingstukken opnieuw toegewezen"] = reassigned

        # The audit trail keeps the name it recorded and loses the broken link.
        for column, valid in (
            (AuditLog.user_id, user_ids),
            (AuditLog.wardrobe_id, {w.id for w in db.query(Wardrobe).all()}),
        ):
            db.query(AuditLog).filter(
                column.isnot(None), column.notin_(valid)
            ).update({column: None}, synchronize_session=False)
        db.commit()

        if removed:
            log.warning(
                "Resten van eerder verwijderde accounts opgeruimd: %s",
                ", ".join(f"{n} {label}" for label, n in removed.items()),
            )
        else:
            # Say so out loud. Silence here is ambiguous — it reads exactly the
            # same as "this version does not have the sweep yet" — and that
            # ambiguity has already cost someone an evening.
            log.info(
                "Databasecontrole: geen resten van verwijderde accounts gevonden"
                " (%d account(s), %d kast(en))",
                len(user_ids),
                db.query(Wardrobe).count(),
            )
    finally:
        db.close()


def seed_catalog() -> None:
    """Populate the category and size lists on first run, and top up any newly
    introduced default sizes (e.g. shoe sizes, One-size) on existing installs."""
    db = SessionLocal()
    try:
        if db.query(Category).count() == 0:
            db.add_all(
                Category(name=name, position=i)
                for i, name in enumerate(DEFAULT_CATEGORIES)
            )
        existing = {(s.label, s.kind) for s in db.query(SizeOption).all()}
        base = db.query(SizeOption).count()
        for i, (label, kind) in enumerate(DEFAULT_SIZES):
            if (label, kind) not in existing:
                db.add(SizeOption(label=label, kind=kind, position=base + i))
        db.commit()
    finally:
        db.close()


def seed_occasions() -> None:
    """Fill the occasion list on first run, and top up ones added later.

    Same deal as the categories: a release that introduces a new default
    occasion should reach an installation that already has a list, so this
    adds what is missing instead of only filling an empty table.
    """
    db = SessionLocal()
    try:
        existing = {o.name.lower() for o in db.query(OccasionOption).all()}
        base = db.query(OccasionOption).count()
        for i, name in enumerate(DEFAULT_OCCASIONS):
            if name.lower() not in existing:
                db.add(OccasionOption(name=name, position=base + i))
        db.commit()
    finally:
        db.close()


def seed_color_rules() -> None:
    """Seed the editable colour-combination rules from the built-in defaults on
    first run, so admins have a sensible starting point to tweak."""
    db = SessionLocal()
    try:
        if db.query(ColorRule).count() == 0:
            seen: set[tuple[str, str, str]] = set()
            for verdict, pairs in (("good", DEFAULT_GOOD_PAIRS), ("bad", DEFAULT_BAD_PAIRS)):
                for a, b in pairs:
                    lo, hi = sorted((a, b))
                    if (lo, hi, verdict) in seen:
                        continue  # guard against accidental duplicate defaults
                    seen.add((lo, hi, verdict))
                    db.add(ColorRule(color_a=lo, color_b=hi, verdict=verdict))
            db.commit()
    finally:
        db.close()



# ---------------------------------------------------------------------------
# The version marker, and the steps it gates
# ---------------------------------------------------------------------------

def _current_version() -> int:
    """How far this database has already been brought. 0 for anything older."""
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            " id INTEGER PRIMARY KEY CHECK (id = 1),"
            " version INTEGER NOT NULL,"
            " updated_at TEXT)"
        )
        row = conn.exec_driver_sql(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
    return int(row[0]) if row else 0


def _set_version(version: int) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO schema_version (id, version, updated_at) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET version = excluded.version,"
            " updated_at = excluded.updated_at",
            (version, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def migrate_photo_indexes() -> None:
    """Index the columns a photo request looks itself up by.

    ``GET /uploads/<filename>`` finds the garment with
    ``photo_filename = ? OR thumb_filename = ?`` so it can apply that kast's
    access rules. Without these two indexes that is a full scan of ``items``
    per image, and a wardrobe screen asks for dozens of images at once.
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_items_photo_filename"
            " ON items (photo_filename)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_items_thumb_filename"
            " ON items (thumb_filename)"
        )


#: Every schema step, in the order they must run, each with the version it
#: brings the database to. Append only — never renumber, never reorder, and
#: never edit a step that has shipped: somebody's database has already run it.
#:
#: The numbering starts at 1 rather than tracking the old implicit order,
#: because an existing installation has no marker and therefore starts at 0 and
#: runs all of them once. That is safe precisely because each one checks the
#: schema before touching it.
STEPS: tuple[tuple[int, str, object], ...] = (
    # Tables and columns first: every later step uses the ORM, and a mapped
    # column the database does not have makes every query on that table fail.
    (1, "tabellen en kolommen", migrate_schema),
    (2, "kolommen voor SSO-login", migrate_federated_login),
    (3, "tokenversies", migrate_token_versions),
    (4, "sizes.kind", migrate_sizes),
    (5, "uitnodiging zonder kast", migrate_account_invitations),
    (6, "maten unief per soort", migrate_size_uniqueness),
    (7, "kasten", migrate_wardrobes),
    (8, "merken", migrate_brands),
    (9, "index op fotobestandsnamen", migrate_photo_indexes),
    (10, "outfits, weer en tags", migrate_outfits_and_tags),
    # Data repair last, on everything the steps above have settled.
    (11, "opruimcontrole", migrate_orphans),
)

SCHEMA_VERSION = max(version for version, _name, _fn in STEPS)


def run_migrations() -> None:
    """Apply whatever this database has not had yet, and nothing else.

    No step needs an account to exist: on a brand-new database the steps that
    read ``users`` find it empty and return, and on an existing one the accounts
    are already there. So the bootstrap beheerder is a seed, not a migration, and
    lives with the others in :func:`run_seeds` — which means it is created
    *after* these run, and therefore makes its own kast rather than waiting for
    :func:`migrate_wardrobes` to notice it.
    """
    current = _current_version()

    if current >= SCHEMA_VERSION:
        log.info("Database is bij (schemaversie %d); geen migraties nodig.", current)
        if settings.repair_on_start:
            # Asked for on purpose — the obvious thing to want after putting a
            # backup back by hand.
            log.warning(
                "WARDROBE_REPAIR_ON_START staat aan: de opruimcontrole wordt"
                " alsnog uitgevoerd."
            )
            migrate_orphans()
        return

    if current == 0:
        log.info(
            "Geen schemaversie gevonden — alle %d stappen worden één keer"
            " doorlopen. Elke stap kijkt eerst of 'ie nodig is, dus op een"
            " bestaande database doen ze niets.",
            len(STEPS),
        )
    else:
        log.info(
            "Database staat op schemaversie %d, nieuwste is %d — bijwerken.",
            current,
            SCHEMA_VERSION,
        )

    for version, name, step in STEPS:
        if version <= current:
            continue
        log.info("Migratie %d/%d: %s", version, SCHEMA_VERSION, name)
        step()
        # Recorded per step, so a failure halfway leaves the steps that did
        # succeed behind it instead of replaying them on the next boot.
        _set_version(version)

    log.info("Migraties afgerond; database staat op schemaversie %d", SCHEMA_VERSION)


def run_seeds() -> None:
    """The bootstrap account, the catalogue, the occasions and the colour rules.

    Every boot, unlike the migrations, and each one a no-op when there is
    nothing to add. Worth the two counting queries: ``seed_catalog`` does not
    only fill an empty database, it tops up defaults introduced in a later
    release — which is how a shoe size added in a new version reaches an
    installation that already has a catalogue. And ``seed_admin`` is the reason
    a database that somehow lost its last account still lets somebody in.
    """
    seed_admin()
    seed_catalog()
    seed_occasions()
    seed_color_rules()


def prepare_database() -> None:
    """Everything the database needs before the first request arrives."""
    Base.metadata.create_all(bind=engine)
    run_migrations()
    run_seeds()
