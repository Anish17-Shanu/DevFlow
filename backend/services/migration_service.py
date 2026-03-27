from sqlalchemy import inspect, text


class MigrationService:
    @staticmethod
    def apply(sync_connection) -> None:
        inspector = inspect(sync_connection)
        table_names = set(inspector.get_table_names())

        if "executions" in table_names:
            columns = {column["name"] for column in inspector.get_columns("executions")}
            if "updated_at" not in columns:
                sync_connection.execute(text("ALTER TABLE executions ADD COLUMN updated_at TIMESTAMP"))
                sync_connection.execute(
                    text(
                        "UPDATE executions "
                        "SET updated_at = COALESCE(finished_at, started_at, created_at) "
                        "WHERE updated_at IS NULL"
                    )
                )
