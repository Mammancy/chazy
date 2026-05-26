from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.admin_users import (
    AdminCreateRequest,
    AdminUserActivityResponse,
    AdminUserListResponse,
    AdminUserProfileResponse,
    AdminUserStatusResponse,
    AdminUserSummaryResponse,
)
from app.services.auth_service import AuthService


class AdminUserService:
    def __init__(self, db: Session):
        self.db = db

    def list_users(
        self,
        *,
        search: str | None = None,
        status: str = "all",
        limit: int = 25,
        offset: int = 0,
    ) -> AdminUserListResponse:
        query = select(User)
        if search:
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    User.email.ilike(term),
                    User.full_name.ilike(term),
                    User.phone_number.ilike(term),
                    User.country.ilike(term),
                    User.state.ilike(term),
                )
            )
        if status == "active":
            query = query.where(User.is_active.is_(True))
        elif status == "inactive":
            query = query.where(User.is_active.is_(False))

        total = len(self.db.scalars(query).all())
        users = list(
            self.db.scalars(
                query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
            ).all()
        )
        return AdminUserListResponse(
            users=[self._summary(user) for user in users],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_profile(self, user_id: int) -> AdminUserProfileResponse:
        user = self._user_or_error(user_id)
        return AdminUserProfileResponse(
            user=self._summary(user),
            activity_history=self._activity_history(user_id),
        )

    def update_status(self, user_id: int, is_active: bool) -> AdminUserStatusResponse:
        user = self._user_or_error(user_id)
        user.is_active = is_active
        self.db.commit()
        self.db.refresh(user)
        state = "activated" if is_active else "deactivated"
        return AdminUserStatusResponse(
            success=True,
            message=f"User {state} successfully.",
            user=self._summary(user),
        )

    def delete_user(self, user_id: int) -> AdminUserStatusResponse:
        user = self._user_or_error(user_id)
        summary = self._summary(user)
        user.email = f"deleted-user-{user.id}@deleted.local"
        user.full_name = "Deleted User"
        user.phone_number = None
        user.external_id = None
        user.password_hash = None
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        user.is_active = False
        self.db.commit()
        return AdminUserStatusResponse(
            success=True,
            message="User deleted successfully. The account was anonymized and deactivated.",
            user=summary,
        )

    def create_admin(self, payload: AdminCreateRequest) -> AdminUserStatusResponse:
        user = AuthService(self.db).create_user(payload, role="admin")
        return AdminUserStatusResponse(
            success=True,
            message="Administrator created successfully.",
            user=self._summary(user),
        )

    def _summary(self, user: User) -> AdminUserSummaryResponse:
        conversation_count = self.db.query(Conversation).filter(Conversation.user_id == user.id).count()
        message_count = self.db.query(Message).filter(Message.user_id == user.id).count()
        last_message = self.db.scalar(
            select(Message)
            .where(Message.user_id == user.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_conversation = self.db.scalar(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        activity_dates = [value for value in [last_message.created_at if last_message else None, last_conversation.updated_at if last_conversation else None] if value]
        return AdminUserSummaryResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
            country=user.country,
            state=user.state,
            timezone=user.timezone,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            conversation_count=conversation_count,
            message_count=message_count,
            last_activity_at=max(activity_dates) if activity_dates else None,
        )

    def _activity_history(self, user_id: int) -> list[AdminUserActivityResponse]:
        activity: list[AdminUserActivityResponse] = []
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.user_id == user_id)
                .order_by(Message.created_at.desc())
                .limit(12)
            ).all()
        )
        for message in messages:
            activity.append(
                AdminUserActivityResponse(
                    type="message",
                    title=f"{message.role.title()} message",
                    detail=(message.content or "")[:180],
                    occurred_at=message.created_at,
                )
            )
        conversations = list(
            self.db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(8)
            ).all()
        )
        for conversation in conversations:
            activity.append(
                AdminUserActivityResponse(
                    type="conversation",
                    title=conversation.title or "Conversation",
                    detail=conversation.status,
                    occurred_at=conversation.updated_at,
                )
            )
        activity.sort(key=lambda item: item.occurred_at, reverse=True)
        return activity[:20]

    def _user_or_error(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found.")
        return user
