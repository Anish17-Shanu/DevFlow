from pathlib import Path

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DEVELOPMENT_API_KEY = "devflow-dev-key"


class Settings(BaseSettings):
    environment: str = "development"
    app_name: str = "DevFlow"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'devflow.db').as_posix()}"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=30.0, ge=1, le=120)
    auto_migrate: bool = True

    worker_count: int = Field(default=4, ge=1, le=64)
    worker_poll_interval_ms: int = Field(default=250, ge=100, le=10000)
    worker_heartbeat_interval_seconds: int = Field(default=5, ge=1, le=300)
    worker_shutdown_grace_seconds: int = Field(default=20, ge=1, le=300)
    worker_instance_id: str = ""
    inline_workers_enabled: bool = True
    queue_lease_seconds: int = Field(default=30, ge=5, le=3600)
    queue_poison_max_attempts: int = Field(default=5, ge=1, le=100)
    queue_aging_seconds: int = Field(default=60, ge=1, le=3600)
    max_concurrent_tasks_per_workflow: int = Field(default=16, ge=1, le=1000)
    max_task_timeout_seconds: int = Field(default=600, ge=1, le=86400)
    task_retention_days: int = Field(default=30, ge=1, le=3650)

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    docs_enabled: bool = True
    log_level: str = "INFO"
    log_format: str = "json"
    queue_name: str = "database"
    realtime_poll_interval_ms: int = Field(default=1000, ge=250, le=10000)
    realtime_bus: str = "auto"
    realtime_channel: str = "devflow_events"
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=50_000_000)
    request_timeout_seconds: float = Field(default=30.0, ge=1, le=300)

    bootstrap_api_key: str = DEVELOPMENT_API_KEY
    bootstrap_tenant_name: str = "Default tenant"
    auth_cache_ttl_seconds: int = Field(default=30, ge=0, le=300)
    rate_limit_requests_per_minute: int = Field(default=600, ge=1, le=1_000_000)
    rate_limit_burst: int = Field(default=100, ge=1, le=100_000)
    rate_limit_backend: str = "memory"
    redis_url: str = ""
    max_concurrent_executions_per_tenant: int = Field(default=20, ge=1, le=10_000)
    secret_encryption_key: str = ""

    metrics_enabled: bool = True
    otel_exporter_otlp_endpoint: str = ""

    watchdog_interval_seconds: int = Field(default=15, ge=2, le=600)
    scheduler_interval_seconds: int = Field(default=15, ge=2, le=600)
    retention_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    log_retention_days: int = Field(default=30, ge=1, le=3650)
    execution_retention_days: int = Field(default=90, ge=1, le=3650)
    queue_retention_days: int = Field(default=7, ge=1, le=3650)
    worker_retention_days: int = Field(default=7, ge=1, le=3650)

    webhook_timeout_seconds: float = Field(default=10.0, ge=1, le=60)
    webhook_max_attempts: int = Field(default=5, ge=1, le=20)
    allow_private_task_targets: bool = False

    model_config = SettingsConfigDict(env_prefix="DEVFLOW_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.realtime_bus not in {"auto", "postgres", "off"}:
            raise ValueError("DEVFLOW_REALTIME_BUS must be one of: auto, postgres, off.")
        if self.is_production:
            if not self.cors_origin_list:
                raise ValueError("DEVFLOW_CORS_ORIGINS must list at least one origin in production.")
            if self.bootstrap_api_key == DEVELOPMENT_API_KEY or len(self.bootstrap_api_key) < 24:
                raise ValueError("DEVFLOW_BOOTSTRAP_API_KEY must be a unique secret of at least 24 characters.")
            if not self.secret_encryption_key:
                raise ValueError("DEVFLOW_SECRET_ENCRYPTION_KEY must be set in production.")
            if self.auto_migrate:
                raise ValueError("DEVFLOW_AUTO_MIGRATE must be false in production; run migrations as a release job.")
        return self

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
