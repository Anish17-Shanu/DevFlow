from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "DevFlow"
    api_prefix: str = "/api"
    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'devflow.db').as_posix()}"
    worker_count: int = 4
    worker_poll_interval_ms: int = 250
    inline_workers_enabled: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_prefix="DEVFLOW_", env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
