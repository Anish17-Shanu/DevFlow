from __future__ import annotations

from sqlalchemy import func, select

from backend.core.config import settings
from backend.core.security import ApiError, Principal
from backend.core.time import utc_now
from backend.handlers.registry import registry
from backend.models.entities import (
    AuditLog,
    WebhookDelivery,
    WebhookEndpoint,
    Workflow,
    WorkflowSchedule,
)
from backend.schemas.ops import SecretCreate, WebhookCreate
from backend.schemas.workflow import ScheduleCreate
from backend.services.audit_service import AuditService
from backend.services.scheduler_service import compute_next_run
from backend.services.secret_service import SecretService


class OpsController:
    def __init__(self, session, runtime=None):
        self.session = session
        self.runtime = runtime

    async def list_audit(self, principal: Principal, limit: int, offset: int):
        principal.require("admin")
        conditions = [AuditLog.tenant_id == principal.tenant_id]
        total = await self.session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
        result = await self.session.execute(
            select(AuditLog).where(*conditions).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
        return {"items": list(result.scalars()), "total": int(total or 0), "limit": limit, "offset": offset}

    async def create_secret(self, principal: Principal, payload: SecretCreate):
        principal.require("admin")
        record = await SecretService(self.session).create(principal.tenant_id, payload)
        AuditService.write(self.session, principal, "secret.created", "secret", record.id, {"name": record.name})
        await self.session.commit()
        return record

    async def list_secrets(self, principal: Principal):
        principal.require("admin")
        return await SecretService(self.session).list(principal.tenant_id)

    async def delete_secret(self, principal: Principal, name: str):
        principal.require("admin")
        await SecretService(self.session).delete(principal.tenant_id, name)
        AuditService.write(self.session, principal, "secret.deleted", "secret", name, {"name": name})
        await self.session.commit()

    async def create_webhook(self, principal: Principal, payload: WebhookCreate):
        principal.require("admin")
        endpoint = WebhookEndpoint(
            tenant_id=principal.tenant_id,
            url=payload.url,
            secret=payload.secret,
            events=payload.events,
            is_active=payload.is_active,
        )
        self.session.add(endpoint)
        await self.session.commit()
        await self.session.refresh(endpoint)
        AuditService.write(
            self.session, principal, "webhook.created", "webhook", endpoint.id, {"events": payload.events}
        )
        await self.session.commit()
        return endpoint

    async def list_webhooks(self, principal: Principal):
        principal.require("admin")
        result = await self.session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.tenant_id == principal.tenant_id)
            .order_by(WebhookEndpoint.created_at.desc())
        )
        return list(result.scalars())

    async def delete_webhook(self, principal: Principal, webhook_id: str):
        principal.require("admin")
        endpoint = await self.session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == webhook_id, WebhookEndpoint.tenant_id == principal.tenant_id
            )
        )
        if endpoint is None:
            raise ApiError(404, "not_found", "Webhook not found.")
        await self.session.delete(endpoint)
        AuditService.write(self.session, principal, "webhook.deleted", "webhook", webhook_id)
        await self.session.commit()

    async def list_deliveries(self, principal: Principal, limit: int, offset: int):
        principal.require("admin")
        conditions = [WebhookDelivery.tenant_id == principal.tenant_id]
        total = await self.session.scalar(select(func.count()).select_from(WebhookDelivery).where(*conditions))
        result = await self.session.execute(
            select(WebhookDelivery)
            .where(*conditions)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return {"items": list(result.scalars()), "total": int(total or 0), "limit": limit, "offset": offset}

    async def create_schedule(self, principal: Principal, workflow_id: str, payload: ScheduleCreate):
        principal.require("operator")
        workflow = await self.session.scalar(
            select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.tenant_id == principal.tenant_id,
                Workflow.is_archived.is_(False),
            )
        )
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")
        schedule = WorkflowSchedule(
            tenant_id=principal.tenant_id,
            workflow_id=workflow.id,
            cron=payload.cron,
            interval_seconds=payload.interval_seconds,
            next_run_at=utc_now(),
            is_enabled=True,
        )
        schedule.next_run_at = compute_next_run(schedule)
        self.session.add(schedule)
        await self.session.commit()
        await self.session.refresh(schedule)
        AuditService.write(
            self.session,
            principal,
            "schedule.created",
            "schedule",
            schedule.id,
            {"workflow_id": workflow.id, "cron": payload.cron, "interval_seconds": payload.interval_seconds},
        )
        await self.session.commit()
        return schedule

    async def list_schedules(self, principal: Principal, workflow_id: str):
        result = await self.session.execute(
            select(WorkflowSchedule)
            .where(
                WorkflowSchedule.tenant_id == principal.tenant_id,
                WorkflowSchedule.workflow_id == workflow_id,
            )
            .order_by(WorkflowSchedule.created_at.desc())
        )
        return list(result.scalars())

    async def delete_schedule(self, principal: Principal, schedule_id: str):
        principal.require("operator")
        schedule = await self.session.scalar(
            select(WorkflowSchedule).where(
                WorkflowSchedule.id == schedule_id, WorkflowSchedule.tenant_id == principal.tenant_id
            )
        )
        if schedule is None:
            raise ApiError(404, "not_found", "Schedule not found.")
        await self.session.delete(schedule)
        AuditService.write(self.session, principal, "schedule.deleted", "schedule", schedule_id)
        await self.session.commit()

    async def list_dead_letters(self, principal: Principal, limit: int, offset: int):
        principal.require("admin")
        records = await self.runtime.queue.list_dead_letters(principal.tenant_id, limit, offset)
        total = await self.runtime.queue.count_dead_letters(principal.tenant_id)
        return {"items": records, "total": total, "limit": limit, "offset": offset}

    async def replay_dead_letter(self, principal: Principal, job_id: str):
        principal.require("operator")
        queue = self.runtime.queue
        record = await queue.get_dead_letter(principal.tenant_id, job_id)
        if record is None:
            raise ApiError(404, "not_found", "Dead-lettered job not found.")
        await self.runtime.execution_service.retry_task(
            self.session,
            principal.tenant_id,
            record.execution_id,
            record.execution_task_id,
            actor=f"{principal.key_name} ({principal.role})",
        )
        await queue.resolve_dead_letter(principal.tenant_id, job_id)
        AuditService.write(
            self.session,
            principal,
            "queue.dead_letter_replayed",
            "queue_job",
            job_id,
            {"execution_id": record.execution_id},
        )
        await self.session.commit()
        return {"replayed": True, "job_id": job_id}

    async def diagnostics(self, principal: Principal):
        principal.require("admin")
        runtime = self.runtime
        queue_stats = await runtime.queue.stats(None)
        workers = await runtime.worker_manager.snapshots()
        enabled_schedules = await self.session.scalar(
            select(func.count()).select_from(WorkflowSchedule).where(WorkflowSchedule.is_enabled.is_(True))
        )
        return {
            "version": settings.app_version,
            "environment": settings.environment,
            "queue": queue_stats,
            "workers": [
                {
                    "worker_id": worker.worker_id,
                    "state": worker.state,
                    "last_seen_at": worker.last_seen_at,
                    "last_error": worker.last_error,
                }
                for worker in workers
            ],
            "dead_letters": int(await runtime.queue.dead_letter_count()),
            "stale_leases": int(await runtime.queue.stale_lease_count()),
            "handlers": registry.names(),
            "scheduler": {"enabled_schedules": int(enabled_schedules or 0)},
            "websockets": await runtime.realtime.connection_count(),
            "config": {
                "queue_lease_seconds": settings.queue_lease_seconds,
                "worker_count": settings.worker_count,
                "max_concurrent_tasks_per_workflow": settings.max_concurrent_tasks_per_workflow,
                "max_task_timeout_seconds": settings.max_task_timeout_seconds,
                "rate_limit_requests_per_minute": settings.rate_limit_requests_per_minute,
            },
        }
