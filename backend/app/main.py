import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from ._version import __version__
from .config import settings
from .database import engine
from .logging_setup import configure_logging, get_logger
from .migrations import prepare_database
from .routers.photos import is_https
from .routers import (
    admin_log,
    auth,
    backups,
    catalog,
    color_rules,
    imports,
    invitations,
    items,
    matches,
    oidc,
    photos,
    users,
    wardrobes,
)
from .settings_report import report as report_settings

# Logging is configured before anything else runs, so even the startup
# migrations below end up in the container log and the in-app log screen.
configure_logging(settings.log_level)
log = get_logger("app")
request_log = get_logger("request")
health_log = get_logger("health")

app = FastAPI(title="Kledingkast", version=__version__)

# No CORS at all unless an operator names an origin. The app serves its own
# frontend from its own origin, and the Vite dev server proxies /api and
# /uploads to the backend (see frontend/vite.config.ts), so a cross-origin
# request never arises in either setup — the old "allow every origin" was
# answering a question nobody asked. It was harmless only for as long as the
# API authorised nothing with cookies, and photos already do.
if settings.cors_origin_list:
    log.info("CORS toegestaan voor: %s", ", ".join(settings.cors_origin_list))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers the browser needs in order to protect the app for us.

    The login token lives in ``localStorage``, where a script injected into the
    page could read it. A Content-Security-Policy that refuses to run anything
    but this origin's own scripts is by far the strongest thing available
    against that, and it costs nothing here because the app loads no third-party
    anything.

    Skipped for photos: those are authorised by cookie and served straight off
    disk, and a policy on an image is meaningless.
    """
    response = await call_next(request)
    if request.url.path.startswith("/uploads/"):
        return response
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if settings.content_security_policy.strip():
        response.headers.setdefault(
            "Content-Security-Policy", settings.content_security_policy.strip()
        )
    # Only over https, and only when asked: HSTS is a promise the browser keeps
    # for as long as it says, and making it before the certificate is sorted
    # locks people out of their own wardrobe.
    if settings.hsts_seconds > 0 and is_https(request):
        response.headers.setdefault(
            "Strict-Transport-Security", f"max-age={settings.hsts_seconds}"
        )
    return response

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



log.info("Kledingkast %s start op, database: %s", __version__, settings.db_path)
# Before anything else does any work: what the app thinks its configuration is,
# and where each piece of it came from. Half of self-hosting is finding out
# whether the .env was read at all.
report_settings()
# Schema first, then the seeds that top themselves up. Which of those run, and
# why only some of them run every boot, is explained in app/migrations.py.
prepare_database()
if settings.oidc_configured:
    log.info(
        "SSO (OpenID Connect) staat aan voor %s; beheerdersgroep: %s",
        settings.oidc_issuer_url,
        settings.oidc_admin_group or "(geen — rollen blijven zoals de app ze heeft)",
    )
elif settings.oidc_enabled:
    log.warning(
        "WARDROBE_OIDC_ENABLED staat aan, maar issuer, client-id of"
        " client-secret ontbreekt — SSO blijft uit."
    )
if settings.admin_password in ("changeme", "change-me"):
    log.warning(
        "Het beheerderswachtwoord uit de omgeving is nog het voorbeeld"
        " ('%s'). Wijzig het in de app onder Instellingen → Wachtwoord wijzigen.",
        settings.admin_password,
    )
log.info("Migraties en seeds afgerond; app is klaar")

app.include_router(auth.router)
app.include_router(backups.router)
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
app.include_router(oidc.router)

# Uploaded photos. Served by a router rather than a StaticFiles mount, so each
# photo goes through the access check of the wardrobe it belongs to.
app.include_router(photos.router)


@app.get("/api/health")
def health(response: Response):
    """Whether this container can actually do its job.

    It used to answer ``{"status": "ok"}`` unconditionally, which made it useless
    for the one thing a health check is for: it would have said "fine" with an
    unreadable database or a full disk. So it touches both things the app cannot
    work without, and answers 503 when one of them is broken — which is what
    lets Docker's restart policy act on a container that is up but wedged,
    rather than only on one that has exited.

    Deliberately cheap and unauthenticated: one trivial query and one stat, so
    it can be polled every fifteen seconds without showing up in the logs.
    """
    checks: dict[str, str] = {}
    healthy = True

    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        healthy = False
        checks["database"] = "onbereikbaar"
        health_log.error("Healthcheck: de database is niet te lezen: %s", exc)

    try:
        probe = settings.uploads_dir / ".health"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
        checks["uploads"] = "ok"
    except Exception as exc:
        healthy = False
        checks["uploads"] = "niet beschrijfbaar"
        health_log.error(
            "Healthcheck: er kan niet naar %s geschreven worden: %s",
            settings.uploads_dir,
            exc,
        )

    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks, "version": __version__}


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
