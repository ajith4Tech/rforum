"""
Audit logging — fire-and-forget writes of security-critical events.

Callers use log_audit(...) which enqueues the DB write to the task queue.
A write failure is logged but never propagates to the caller.
"""
import logging
import uuid
from typing import Any

from app.database import async_session
from app.models import AuditLog
from app.tasks import task_queue

logger = logging.getLogger("rforum.audit")


# ── Action / entity constants ─────────────────────────────────────────────────

class AuditAction:
    USER_REGISTERED = "USER_REGISTERED"
    SUPER_ADMIN_CREATED = "SUPER_ADMIN_CREATED"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_SUCCESS = "PASSWORD_RESET_SUCCESS"
    INVITE_CODE_REJECTED = "INVITE_CODE_REJECTED"
    SESSION_INVALIDATED = "SESSION_INVALIDATED"


class AuditEntity:
    AUTH = "AUTH"
    USER = "USER"
    SETTINGS = "SETTINGS"


# ── Internal writer (runs in task queue) ──────────────────────────────────────

async def _write(
    action: str,
    entity_type: str,
    user_id: uuid.UUID | None,
    entity_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    metadata: dict[str, Any] | None,
    trace_id: str | None,
) -> None:
    try:
        async with async_session() as db:
            db.add(AuditLog(
                action=action,
                entity_type=entity_type,
                user_id=user_id,
                entity_id=entity_id,
                ip_address=ip_address,
                user_agent=user_agent,
                log_metadata={**(metadata or {}), "trace_id": trace_id},
            ))
            await db.commit()
    except Exception as exc:
        logger.error(
            "audit_write_failed",
            extra={"action": action, "trace_id": trace_id, "error": str(exc)},
        )


# ── Public interface ──────────────────────────────────────────────────────────

def log_audit(
    action: str,
    entity_type: str,
    *,
    user_id: uuid.UUID | None = None,
    entity_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Enqueue an audit log write. Non-blocking. Never raises."""
    task_queue.enqueue(
        _write,
        action,
        entity_type,
        user_id,
        entity_id,
        ip_address,
        user_agent,
        metadata,
        trace_id,
    )
