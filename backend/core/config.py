from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    environment: str = "development"
    app_name: str = "DevFlow"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'devflow.db').as_posix()}"
    worker_count: int = Field(default=4, ge=1, le=64)
    worker_poll_interval_ms: int = Field(default=250, ge=100, le=10000)
    worker_heartbeat_interval_seconds: int = Field(default=5, ge=1, le=300)
    inline_workers_enabled: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    docs_enabled: bool = True
    log_level: str = "INFO"
    queue_name: str = "database"
    queue_lease_seconds: int = Field(default=30, ge=5, le=3600)
    realtime_poll_interval_ms: int = Field(default=1000, ge=250, le=10000)

    model_config = SettingsConfigDict(env_prefix="DEVFLOW_", env_file=".env", extra="ignore")

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if self.is_production:
            return origins
        return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
