from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Category, SizeOption, User
from .routers import auth, catalog, imports, items, matches, users
from .security import hash_password

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

app = FastAPI(title="Kledingkast", version="1.0.0")

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
        existing = {s.label for s in db.query(SizeOption).all()}
        base = db.query(SizeOption).count()
        for i, (label, kind) in enumerate(DEFAULT_SIZES):
            if label not in existing:
                db.add(SizeOption(label=label, kind=kind, position=base + i))
        db.commit()
    finally:
        db.close()


seed_admin()
migrate_sizes()
seed_catalog()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(items.router)
app.include_router(matches.router)
app.include_router(catalog.categories_router)
app.include_router(catalog.sizes_router)
app.include_router(imports.router)

# Uploaded photos.
app.mount("/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}


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
