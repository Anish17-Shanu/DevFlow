from backend.models.entities import ExecutionLog


class LogService:
    @staticmethod
    async def write(session, execution_id: str, message: str, level: str = "INFO", task_id: str | None = None) -> None:
        session.add(
            ExecutionLog(
                execution_id=execution_id,
                task_id=task_id,
                level=level,
                message=message,
            )
        )
