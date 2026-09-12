from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, overridable via environment variables."""

    model_config = SettingsConfigDict(env_prefix="WARDROBE_", env_file=".env", extra="ignore")

    # Where the SQLite database and uploaded photos live. Mount this as a
    # Docker volume so your wardrobe survives container restarts.
    data_dir: Path = Path("./data")

    # Secret used to sign login tokens. CHANGE THIS in production.
    secret_key: str = "change-me-please-set-WARDROBE_SECRET_KEY"

    # How long a login stays valid (minutes). Default: 30 days.
    access_token_expire_minutes: int = 60 * 24 * 30

    # The address the app is reached at from a browser, e.g.
    # "https://kast.jouwdomein.nl". Only needed for federated login: the
    # redirect URI handed to the identity provider has to match the one
    # registered there exactly, and a reverse proxy is free to rewrite every
    # header this would otherwise be guessed from. Left empty the app derives
    # it from the request, which works as long as the proxy forwards
    # X-Forwarded-Proto and Host faithfully.
    public_url: str = ""

    # Bootstrap admin account, created on first startup if no users exist.
    admin_username: str = "admin"
    admin_password: str = "changeme"
    admin_display_name: str = "Beheerder"

    # Max upload size in megabytes.
    max_upload_mb: int = 15

    # How chatty the application log is. DEBUG also logs every read request;
    # INFO logs changes, warnings and errors. Visible in the container log and
    # in the app under Instellingen → Logboek.
    log_level: str = "INFO"

    # ---- Hardening ----
    #
    # Consecutive failed logins allowed before the answer becomes 429, and the
    # first wait once it does. Each further failure doubles it, up to 15
    # minutes. A correct password clears the count.
    login_max_attempts: int = 5
    login_lockout_seconds: int = 30

    # Shortest password the app will accept when one is *set*. Existing
    # passwords are not affected: nobody is locked out by raising this, they
    # only meet it the next time they choose one.
    min_password_length: int = 8

    # Browsers that may call the API from another origin, comma-separated.
    # Empty means none, which is the right answer for every normal install:
    # the app serves its own frontend from the same origin, and the Vite dev
    # server proxies /api, so cross-origin requests never arise. Set this only
    # if you host the frontend somewhere else.
    cors_origins: str = ""

    # Whether the photo cookie carries the Secure flag. "auto" decides per
    # request: set on https, left off on plain http, where a secure cookie
    # would simply never be sent and photos would break. "true"/"false" force
    # it either way.
    cookie_secure: str = "auto"

    # Content-Security-Policy sent with the app's own pages. The default keeps
    # everything on this origin, which is the strongest mitigation available
    # for a token that lives in localStorage. Set to an empty string to send
    # no policy at all (e.g. when your reverse proxy sets its own).
    content_security_policy: str = (
        "default-src 'self'; "
        "script-src 'self'; "
        # React writes inline style attributes all over this app, and those
        # need 'unsafe-inline' in style-src. It does not weaken script-src.
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )

    # Send Strict-Transport-Security on https requests. Off by default: it is a
    # promise a browser remembers for a year, and turning it on before your
    # certificate is sorted locks people out of their own wardrobe.
    hsts_seconds: int = 0

    # Let the photo-URL and webshop-import features reach private addresses.
    # Off by default: those features take a URL from any signed-in user, and
    # the server sits on the same network as everything else you self-host.
    fetch_allow_private: bool = False

    # ---- Federated login (OpenID Connect) ----
    #
    # Off unless an issuer, a client id and a secret are all present: a half
    # configured provider must not put a broken button on the login screen.
    oidc_enabled: bool = False
    #: Base URL of the provider, e.g.
    #: "https://auth.jouwdomein.nl/application/o/kledingkast/". Discovery
    #: appends /.well-known/openid-configuration; a full discovery URL is
    #: accepted too and trimmed back.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    #: Scopes to ask for. "openid" is added if you leave it out. Group
    #: membership is not in the standard set, hence "groups".
    oidc_scopes: str = "openid profile email groups"
    #: Claim holding the user's groups. A dotted path reaches into nested
    #: claims, which is how Keycloak's "realm_access.roles" is read.
    oidc_groups_claim: str = "groups"
    #: Membership of this group makes someone a beheerder; anyone without it
    #: becomes (or stays) an ordinary user. Empty disables the mapping
    #: altogether and leaves the role as the app has it.
    oidc_admin_group: str = ""
    #: When set, only members of these groups (comma-separated) may sign in
    #: at all. Empty lets every account the provider authenticates through.
    oidc_allowed_groups: str = ""
    #: Create an account the first time someone signs in who has none. Off by
    #: default, which keeps the installation invitation-only: without it an
    #: unknown person is turned away unless they hold an invitation link.
    oidc_auto_create: bool = False
    #: Adopt an existing local account when the provider's username matches it
    #: exactly. Off by default because it trusts the provider with the
    #: username: only turn it on to bootstrap accounts that predate SSO.
    oidc_link_by_username: bool = False
    #: Text on the login button.
    oidc_button_label: str = "Inloggen met SSO"
    #: Ask the provider to end its own session too when signing out here.
    oidc_logout_redirect: bool = False

    # Whether the login screen shows the username/password form up front.
    # This is a tidiness setting, not a security control: the password
    # endpoint keeps working either way, on purpose, so an unreachable or
    # misconfigured provider can never lock you out of your own wardrobe.
    local_login: bool = True

    # Directory containing the built frontend (index.html + assets). Relative
    # paths are resolved against the backend package root. In the Docker image
    # the Vite build is copied to "static". Left empty during local dev.
    frontend_dir: str = "static"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "wardrobe.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def oidc_configured(self) -> bool:
        """True only when federated login can actually complete a round trip."""
        return bool(
            self.oidc_enabled
            and self.oidc_issuer.strip()
            and self.oidc_client_id.strip()
            and self.oidc_client_secret.strip()
        )

    @property
    def oidc_issuer_url(self) -> str:
        """The issuer, with a pasted discovery URL trimmed back to its base."""
        issuer = self.oidc_issuer.strip().rstrip("/")
        suffix = "/.well-known/openid-configuration"
        if issuer.endswith(suffix):
            issuer = issuer[: -len(suffix)]
        return issuer

    @property
    def oidc_scope_list(self) -> list[str]:
        """Requested scopes, always including "openid"."""
        scopes = [s for s in self.oidc_scopes.replace(",", " ").split() if s]
        if "openid" not in scopes:
            scopes.insert(0, "openid")
        return scopes

    @property
    def oidc_allowed_group_list(self) -> list[str]:
        return [g.strip() for g in self.oidc_allowed_groups.split(",") if g.strip()]


settings = Settings()

# Ensure data directories exist at import time.
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
