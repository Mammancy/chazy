from __future__ import annotations

from sqlalchemy import bindparam, delete, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.conversation import Conversation
from app.models.conversation_scenario import ConversationScenarioSession, ConversationScenarioTurn
from app.models.learning_analytics import LearningIssue
from app.models.memory import Memory
from app.models.memory_summary import MemorySummary
from app.models.message import Message
from app.models.placement_assessment import PlacementAssessmentAnswer, PlacementAssessmentSession
from app.models.pronunciation import PronunciationPracticeAttempt, PronunciationPracticeSession
from app.models.refresh_token import RefreshToken
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.user import User
from app.models.vocabulary_notebook import (
    VocabularyNotebookEntry,
    VocabularyReviewSession,
    VocabularyReviewSessionItem,
)
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

        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        users = list(
            self.db.scalars(
                query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
            ).all()
        )
        summaries = self._summaries(users)
        return AdminUserListResponse(
            users=summaries,
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

    def purge_user(self, user_id: int) -> None:
        user = self._user_or_error(user_id)
        if user.is_active:
            raise PermissionError("Active users must be deleted before they can be purged.")
        if not self._is_deleted_user(user):
            raise PermissionError("Only deleted and anonymized users can be purged.")

        conversation_ids = list(
            self.db.scalars(select(Conversation.id).where(Conversation.user_id == user_id)).all()
        )
        message_ids = list(
            self.db.scalars(select(Message.id).where(Message.user_id == user_id)).all()
        )
        if conversation_ids:
            conversation_message_ids = list(
                self.db.scalars(
                    select(Message.id).where(Message.conversation_id.in_(conversation_ids))
                ).all()
            )
            message_ids = list(set(message_ids + conversation_message_ids))

        scenario_session_filters = [ConversationScenarioSession.user_id == user_id]
        if conversation_ids:
            scenario_session_filters.append(ConversationScenarioSession.conversation_id.in_(conversation_ids))
        scenario_session_ids = list(
            self.db.scalars(
                select(ConversationScenarioSession.id).where(or_(*scenario_session_filters))
            ).all()
        )
        placement_session_ids = list(
            self.db.scalars(
                select(PlacementAssessmentSession.id).where(
                    PlacementAssessmentSession.user_id == user_id
                )
            ).all()
        )
        pronunciation_session_ids = list(
            self.db.scalars(
                select(PronunciationPracticeSession.id).where(
                    PronunciationPracticeSession.user_id == user_id
                )
            ).all()
        )
        vocabulary_entry_filters = [VocabularyNotebookEntry.user_id == user_id]
        if message_ids:
            vocabulary_entry_filters.append(VocabularyNotebookEntry.source_message_id.in_(message_ids))
        vocabulary_entry_ids = list(
            self.db.scalars(
                select(VocabularyNotebookEntry.id).where(or_(*vocabulary_entry_filters))
            ).all()
        )
        vocabulary_review_session_ids = list(
            self.db.scalars(
                select(VocabularyReviewSession.id).where(
                    VocabularyReviewSession.user_id == user_id
                )
            ).all()
        )

        if scenario_session_ids or message_ids:
            turn_filters = []
            if scenario_session_ids:
                turn_filters.append(ConversationScenarioTurn.scenario_session_id.in_(scenario_session_ids))
            if message_ids:
                turn_filters.extend(
                    [
                        ConversationScenarioTurn.user_message_id.in_(message_ids),
                        ConversationScenarioTurn.assistant_message_id.in_(message_ids),
                    ]
                )
            self.db.execute(delete(ConversationScenarioTurn).where(or_(*turn_filters)))

        if vocabulary_review_session_ids:
            self.db.execute(
                delete(VocabularyReviewSessionItem).where(
                    VocabularyReviewSessionItem.review_session_id.in_(vocabulary_review_session_ids)
                )
            )
        if vocabulary_entry_ids:
            self.db.execute(
                delete(VocabularyReviewSessionItem).where(
                    VocabularyReviewSessionItem.entry_id.in_(vocabulary_entry_ids)
                )
            )

        if placement_session_ids:
            self.db.execute(
                delete(PlacementAssessmentAnswer).where(
                    PlacementAssessmentAnswer.assessment_session_id.in_(placement_session_ids)
                )
            )
        if pronunciation_session_ids:
            self.db.execute(
                delete(PronunciationPracticeAttempt).where(
                    PronunciationPracticeAttempt.practice_session_id.in_(pronunciation_session_ids)
                )
            )

        self._delete_optional_emotional_rows(
            user_id=user_id,
            conversation_ids=conversation_ids,
            message_ids=message_ids,
        )
        self.db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        self.db.execute(delete(AchievementAward).where(AchievementAward.user_id == user_id))
        self.db.execute(delete(LearningIssue).where(LearningIssue.user_id == user_id))
        self.db.execute(delete(SpeakingChallengeCompletion).where(SpeakingChallengeCompletion.user_id == user_id))
        self.db.execute(delete(PronunciationPracticeAttempt).where(PronunciationPracticeAttempt.user_id == user_id))
        self.db.execute(delete(PronunciationPracticeSession).where(PronunciationPracticeSession.user_id == user_id))
        self.db.execute(delete(VocabularyReviewSession).where(VocabularyReviewSession.user_id == user_id))
        if vocabulary_entry_ids:
            self.db.execute(delete(VocabularyNotebookEntry).where(VocabularyNotebookEntry.id.in_(vocabulary_entry_ids)))
        self.db.execute(delete(PlacementAssessmentSession).where(PlacementAssessmentSession.user_id == user_id))
        if scenario_session_ids:
            self.db.execute(delete(ConversationScenarioSession).where(ConversationScenarioSession.id.in_(scenario_session_ids)))
        self.db.execute(delete(Memory).where(Memory.user_id == user_id))
        self.db.execute(delete(MemorySummary).where(MemorySummary.user_id == user_id))
        if message_ids:
            self.db.execute(delete(Message).where(Message.id.in_(message_ids)))
        if conversation_ids:
            self.db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))

        self.db.delete(user)
        self.db.commit()

    def create_admin(self, payload: AdminCreateRequest) -> AdminUserStatusResponse:
        user = AuthService(self.db).create_user(payload, role="admin")
        return AdminUserStatusResponse(
            success=True,
            message="Administrator created successfully.",
            user=self._summary(user),
        )

    def _summary(self, user: User) -> AdminUserSummaryResponse:
        return self._summaries([user])[0]

    def _summaries(self, users: list[User]) -> list[AdminUserSummaryResponse]:
        user_ids = [user.id for user in users]
        if not user_ids:
            return []

        conversation_counts = dict(
            self.db.execute(
                select(Conversation.user_id, func.count(Conversation.id))
                .where(Conversation.user_id.in_(user_ids))
                .group_by(Conversation.user_id)
            ).all()
        )
        message_counts = dict(
            self.db.execute(
                select(Message.user_id, func.count(Message.id))
                .where(Message.user_id.in_(user_ids))
                .group_by(Message.user_id)
            ).all()
        )
        last_messages = dict(
            self.db.execute(
                select(Message.user_id, func.max(Message.created_at))
                .where(Message.user_id.in_(user_ids))
                .group_by(Message.user_id)
            ).all()
        )
        last_conversations = dict(
            self.db.execute(
                select(Conversation.user_id, func.max(Conversation.updated_at))
                .where(Conversation.user_id.in_(user_ids))
                .group_by(Conversation.user_id)
            ).all()
        )

        summaries = []
        for user in users:
            activity_dates = [
                value
                for value in [last_messages.get(user.id), last_conversations.get(user.id)]
                if value
            ]
            summaries.append(
                AdminUserSummaryResponse(
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
                    conversation_count=int(conversation_counts.get(user.id, 0)),
                    message_count=int(message_counts.get(user.id, 0)),
                    last_activity_at=max(activity_dates) if activity_dates else None,
                )
            )
        return summaries

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

    @staticmethod
    def _is_deleted_user(user: User) -> bool:
        email = (user.email or "").lower()
        external_id = (user.external_id or "").lower()
        name = (user.full_name or "").lower()
        return (
            email.startswith("deleted-user-")
            or external_id.startswith("deleted:")
            or name == "deleted user"
            or user.password_hash is None
        )

    def _delete_optional_emotional_rows(
        self,
        *,
        user_id: int,
        conversation_ids: list[int],
        message_ids: list[int],
    ) -> None:
        table_names = set(inspect(self.db.get_bind()).get_table_names())

        if "message_emotional_tags" in table_names and message_ids:
            self.db.execute(
                text("DELETE FROM message_emotional_tags WHERE message_id IN :message_ids").bindparams(
                    bindparam("message_ids", expanding=True)
                ),
                {"message_ids": tuple(message_ids)},
            )

        if "emotional_memories" not in table_names:
            return

        filters = ["user_id = :user_id"]
        params: dict[str, object] = {"user_id": user_id}
        if conversation_ids:
            filters.append("conversation_id IN :conversation_ids")
            params["conversation_ids"] = tuple(conversation_ids)
        if message_ids:
            filters.append("message_id IN :message_ids")
            params["message_ids"] = tuple(message_ids)

        statement = text(f"DELETE FROM emotional_memories WHERE {' OR '.join(filters)}")
        if conversation_ids:
            statement = statement.bindparams(bindparam("conversation_ids", expanding=True))
        if message_ids:
            statement = statement.bindparams(bindparam("message_ids", expanding=True))

        self.db.execute(statement, params)
