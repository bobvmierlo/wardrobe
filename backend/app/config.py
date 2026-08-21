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

    # Bootstrap admin account, created on first startup if no users exist.
    admin_username: str = "admin"
    admin_password: str = "changeme"
    admin_display_name: str = "Beheerder"

    # Max upload size in megabytes.
    max_upload_mb: int = 15

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


settings = Settings()

# Ensure data directories exist at import time.
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
