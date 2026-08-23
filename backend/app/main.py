import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from ._version import __version__
from .config import settings
from .accounts import purge_wardrobe
from .images import delete_files
from .database import Base, SessionLocal, engine
from .logging_setup import configure_logging, get_logger
from .models import (
    AuditLog,
    Category,
    ColorRule,
    Invitation,
    Item,
    Match,
    MatchSkip,
    SizeOption,
    User,
    Wardrobe,
    WardrobeMember,
)
from .routers import (
    admin_log,
    auth,
    catalog,
    color_rules,
    imports,
    invitations,
    items,
    matches,
    photos,
    users,
    wardrobes,
)
from .security import hash_password
from .suggestions import DEFAULT_BAD_PAIRS, DEFAULT_GOOD_PAIRS

# Logging is configured before anything else runs, so even the startup
# migrations below end up in the container log and the in-app log screen.
configure_logging(settings.log_level)
log = get_logger("app")
request_log = get_logger("request")

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

app = FastAPI(title="Kledingkast", version=__version__)

# Bearer tokens (not cookies) are used, so a permissive CORS policy is safe
# and keeps a separate-origin dev frontend working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Requests that change something, and anything that fails, are worth a log
# line. Successful reads are not — they would drown the log on every screen
# the app paints. Photos and the SPA's own assets are skipped entirely.
_QUIET_PREFIXES = ("/uploads/", "/assets/")

# An invitation token *is* a credential: whoever holds it can join a wardrobe.
# It travels in the URL, so it must never be written to a log that admins (or
# anyone with the container output) can read back.
_SECRET_PATHS = ("/api/invitations/", "/invite/")


def _safe_path(path: str) -> str:
    """The request path with any invitation token replaced by a placeholder."""
    for prefix in _SECRET_PATHS:
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if not rest:
                return path
            # Keep whatever follows the token (e.g. "/accept") — that says what
            # was attempted, and only the token itself is sensitive.
            _, _, tail = rest.partition("/")
            return f"{prefix}<token>" + (f"/{tail}" if tail else "")
    return path


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        request_log.exception(
            "%s %s faalde na %.0f ms", request.method, _safe_path(request.url.path), elapsed
        )
        raise
    elapsed = (time.perf_counter() - started) * 1000
    path = _safe_path(request.url.path)
    if path.startswith(_QUIET_PREFIXES):
        return response
    changes = request.method not in {"GET", "HEAD", "OPTIONS"}
    if response.status_code >= 500:
        level = request_log.error
    elif response.status_code >= 400:
        level = request_log.warning
    elif changes:
        level = request_log.info
    else:
        level = request_log.debug
    level("%s %s → %s (%.0f ms)", request.method, path, response.status_code, elapsed)
    return response


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

        dangling_invites = [
            inv for inv in db.query(Invitation).all()
            if inv.wardrobe_id not in wardrobe_ids or inv.created_by_id not in user_ids
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


# Schema changes first, then data backfills that rely on the ORM.
log.info("Kledingkast %s start op, database: %s", __version__, settings.db_path)
migrate_schema()
seed_admin()
migrate_sizes()
migrate_size_uniqueness()
migrate_wardrobes()
migrate_brands()
migrate_orphans()
seed_catalog()
seed_color_rules()
log.info("Migraties en seeds afgerond; app is klaar")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(wardrobes.router)
app.include_router(items.router)
app.include_router(items.brands_router)
app.include_router(matches.router)
app.include_router(catalog.categories_router)
app.include_router(catalog.sizes_router)
app.include_router(color_rules.router)
app.include_router(imports.router)
app.include_router(invitations.router)
app.include_router(invitations.wardrobe_router)
app.include_router(admin_log.router)

# Uploaded photos. Served by a router rather than a StaticFiles mount, so each
# photo goes through the access check of the wardrobe it belongs to.
app.include_router(photos.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    return {"version": __version__}


# Serve the built frontend (single-page app) when present. In the Docker image
# the Vite build output is copied to ``static/``. During local development the
# frontend runs on its own Vite dev server, so this block is simply skipped.
FRONTEND_DIR = Path(settings.frontend_dir)
if not FRONTEND_DIR.is_absolute():
    FRONTEND_DIR = (Path(__file__).resolve().parent.parent / FRONTEND_DIR).resolve()

if (FRONTEND_DIR / "index.html").exists():
    index_file = FRONTEND_DIR / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Never let the catch-all shadow the API or uploads.
        if full_path.startswith(("api/", "uploads/")):
            return FileResponse(index_file, status_code=404)
        candidate = (FRONTEND_DIR / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index_file)
