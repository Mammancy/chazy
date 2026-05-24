from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User


class AdminAuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        *,
        admin_user: User | None,
        action: str,
        request: Request | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        self.db.add(
            AdminAuditLog(
                admin_user_id=admin_user.id if admin_user is not None else None,
                action=action,
                target_type=target_type,
                target_id=target_id,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:255] or None,
                detail=detail,
                metadata_json=metadata,
            )
        )
        self.db.commit()
