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
DEFAULT_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

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


def seed_catalog() -> None:
    """Populate the category and size lists on first run (empty tables only)."""
    db = SessionLocal()
    try:
        if db.query(Category).count() == 0:
            db.add_all(
                Category(name=name, position=i)
                for i, name in enumerate(DEFAULT_CATEGORIES)
            )
        if db.query(SizeOption).count() == 0:
            db.add_all(
                SizeOption(label=label, position=i)
                for i, label in enumerate(DEFAULT_SIZES)
            )
        db.commit()
    finally:
        db.close()


seed_admin()
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
