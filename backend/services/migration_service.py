from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.core.config import settings

ROOT_DIR = Path(__file__).resolve().parents[2]


class MigrationService:
    @staticmethod
    async def upgrade() -> None:
        await asyncio.to_thread(MigrationService._upgrade_sync)

    @staticmethod
    def _upgrade_sync() -> None:
        config = Config(str(ROOT_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT_DIR / "migrations"))
        config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        config.attributes["skip_logging"] = True
        command.upgrade(config, "head")
