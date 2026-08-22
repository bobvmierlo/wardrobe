from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ._version import __version__
from .config import settings
from .database import Base, SessionLocal, engine
from .models import Category, ColorRule, Item, SizeOption, User, Wardrobe
from .routers import auth, catalog, color_rules, imports, items, matches, users, wardrobes
from .security import hash_password
from .suggestions import DEFAULT_BAD_PAIRS, DEFAULT_GOOD_PAIRS

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
            print(
                f"[kledingkast] Beheerder aangemaakt: '{settings.admin_username}'. "
                "Wijzig het wachtwoord na de eerste login."
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


def migrate_wardrobes() -> None:
    """Give every user a wardrobe and move existing garments into one.

    Introduced when the app gained per-user wardrobes ("kasten") with sharing.
    On existing installs the ``items`` table predates the ``wardrobe_id``
    column, so add it, create one wardrobe per user, and file each garment
    under its creator's wardrobe (falling back to the first admin's).
    """
    Base.metadata.create_all(bind=engine)  # create wardrobes / members tables
    with engine.begin() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(items)").fetchall()
        if cols and not any(c[1] == "wardrobe_id" for c in cols):
            conn.exec_driver_sql(
                "ALTER TABLE items ADD COLUMN wardrobe_id INTEGER REFERENCES wardrobes(id)"
            )

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


seed_admin()
migrate_sizes()
migrate_size_uniqueness()
migrate_wardrobes()
seed_catalog()
seed_color_rules()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(wardrobes.router)
app.include_router(items.router)
app.include_router(matches.router)
app.include_router(catalog.categories_router)
app.include_router(catalog.sizes_router)
app.include_router(color_rules.router)
app.include_router(imports.router)

# Uploaded photos.
app.mount("/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")


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
