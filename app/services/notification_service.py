from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.practice_room import PracticeRoom
from app.models.practice_session import PracticeSession
from app.models.retention import RetentionState
from app.models.speaking_challenge import SpeakingChallengeCompletion
from app.models.speaking_partner import PracticeRequest
from app.schemas.notification import NotificationItemResponse, NotificationListResponse
from app.services.speaking_challenge_service import SpeakingChallengeService


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def list_notifications(self, *, user_id: int) -> NotificationListResponse:
        items = [
            *self._active_room_notifications(user_id=user_id),
            *self._upcoming_session_notifications(user_id=user_id),
            *self._completed_session_notifications(user_id=user_id),
            *self._speaking_request_notifications(user_id=user_id),
            *self._retention_notifications(user_id=user_id),
        ]
        deduped = {item.id: item for item in items}
        notifications = sorted(
            deduped.values(),
            key=lambda item: (self._priority_rank(item.priority), self._aware(item.created_at)),
            reverse=True,
        )[:20]
        return NotificationListResponse(
            notifications=notifications,
            unread_count=len(notifications),
        )

    def _active_room_notifications(self, *, user_id: int) -> list[NotificationItemResponse]:
        rows = self.db.execute(
            select(PracticeSession, PracticeRoom)
            .join(PracticeRoom, PracticeRoom.session_id == PracticeSession.id)
            .where(
                PracticeRoom.status == "active",
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
            )
            .order_by(PracticeRoom.started_at.desc())
        ).all()
        return [
            NotificationItemResponse(
                id=f"practice-room-active-{session.id}",
                type="practice_room_active",
                title="Practice room active",
                body=f"{session.topic or 'Conversation practice'} is live now.",
                href=f"/practice-sessions/{session.id}",
                priority="urgent",
                created_at=self._aware(room.started_at),
                session_id=session.id,
            )
            for session, room in rows
        ]

    def _upcoming_session_notifications(self, *, user_id: int) -> list[NotificationItemResponse]:
        now = datetime.now(timezone.utc)
        soon = now + timedelta(hours=24)
        sessions = self.db.scalars(
            select(PracticeSession)
            .where(
                PracticeSession.status == "scheduled",
                PracticeSession.scheduled_at >= now,
                PracticeSession.scheduled_at <= soon,
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
            )
            .order_by(PracticeSession.scheduled_at.asc())
        ).all()
        return [
            NotificationItemResponse(
                id=f"practice-session-upcoming-{session.id}",
                type="practice_session_upcoming",
                title="Practice session scheduled",
                body=f"{session.topic or 'Conversation practice'} starts {session.scheduled_at.strftime('%b %d, %I:%M %p')}.",
                href=f"/practice-sessions/{session.id}",
                priority="normal",
                created_at=self._aware(session.scheduled_at),
                session_id=session.id,
            )
            for session in sessions
        ]

    def _speaking_request_notifications(self, *, user_id: int) -> list[NotificationItemResponse]:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        requests = self.db.scalars(
            select(PracticeRequest)
            .where(
                PracticeRequest.created_at >= since,
                or_(PracticeRequest.sender_user_id == user_id, PracticeRequest.receiver_user_id == user_id),
            )
            .order_by(PracticeRequest.created_at.desc())
            .limit(10)
        ).all()
        notifications: list[NotificationItemResponse] = []
        for request in requests:
            if request.status == "pending" and request.receiver_user_id == user_id:
                notifications.append(
                    NotificationItemResponse(
                        id=f"speaking-request-received-{request.id}",
                        type="speaking_request_received",
                        title="New speaking practice request",
                        body="A learner sent you a request for conversation practice.",
                        href="/speaking-partners/profile",
                        priority="normal",
                        created_at=self._aware(request.created_at),
                        session_id=None,
                    )
                )
            elif request.status == "pending" and request.sender_user_id == user_id:
                notifications.append(
                    NotificationItemResponse(
                        id=f"speaking-request-sent-{request.id}",
                        type="speaking_request_sent",
                        title="Speaking request sent",
                        body="Your conversation practice request is waiting for a response.",
                        href="/speaking-partners/profile",
                        priority="normal",
                        created_at=self._aware(request.created_at),
                        session_id=None,
                    )
                )
            elif request.status == "accepted" and request.sender_user_id == user_id:
                notifications.append(
                    NotificationItemResponse(
                        id=f"speaking-request-accepted-{request.id}",
                        type="speaking_request_accepted",
                        title="Speaking request accepted",
                        body="Your practice request was accepted. Schedule a practice session.",
                        href=f"/practice-sessions?requestId={request.id}",
                        priority="normal",
                        created_at=self._aware(request.created_at),
                        session_id=None,
                    )
                )
            elif request.status == "accepted" and request.receiver_user_id == user_id:
                notifications.append(
                    NotificationItemResponse(
                        id=f"speaking-request-accepted-by-you-{request.id}",
                        type="speaking_request_accepted",
                        title="Speaking request accepted",
                        body="You accepted a practice request. Schedule a practice session when ready.",
                        href=f"/practice-sessions?requestId={request.id}",
                        priority="normal",
                        created_at=self._aware(request.created_at),
                        session_id=None,
                    )
                )
        return notifications

    def _completed_session_notifications(self, *, user_id: int) -> list[NotificationItemResponse]:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        sessions = self.db.scalars(
            select(PracticeSession)
            .where(
                PracticeSession.status == "completed",
                PracticeSession.updated_at >= since,
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
            )
            .order_by(PracticeSession.updated_at.desc())
            .limit(10)
        ).all()
        return [
            NotificationItemResponse(
                id=f"practice-session-completed-{session.id}",
                type="practice_session_completed",
                title="Practice session completed",
                body=f"{session.topic or 'Conversation practice'} was completed.",
                href=f"/practice-sessions/{session.id}",
                priority="normal",
                created_at=self._aware(session.updated_at),
                session_id=session.id,
            )
            for session in sessions
        ]

    def _retention_notifications(self, *, user_id: int) -> list[NotificationItemResponse]:
        now = datetime.now(timezone.utc)
        today = now.date()
        since = now - timedelta(days=1)
        notifications = [
            NotificationItemResponse(
                id=f"mission-complete-{award.id}",
                type="mission_complete",
                title="Mission complete",
                body=f"{award.title} earned {award.points} XP.",
                href="/dashboard",
                priority="normal",
                created_at=self._aware(award.awarded_at),
                session_id=None,
            )
            for award in self.db.scalars(
                select(AchievementAward)
                .where(
                    AchievementAward.user_id == user_id,
                    AchievementAward.category == "daily_mission",
                    AchievementAward.awarded_at >= since,
                )
                .order_by(AchievementAward.awarded_at.desc())
                .limit(5)
            ).all()
        ]

        completed_today = self.db.query(SpeakingChallengeCompletion).filter(
            SpeakingChallengeCompletion.user_id == user_id,
            SpeakingChallengeCompletion.challenge_date == today,
        ).count()
        state = self.db.scalar(select(RetentionState).where(RetentionState.user_id == user_id).limit(1))
        streak = SpeakingChallengeService(self.db).get_streak(session_id=f"chazy-user-{user_id}", user_id=user_id)
        if completed_today == 0 and streak.current_streak > 0:
            notifications.append(
                NotificationItemResponse(
                    id=f"streak-risk-{user_id}-{today.isoformat()}",
                    type="streak_risk",
                    title="Streak at risk",
                    body=(
                        "Complete one speaking challenge today to protect your streak."
                        if not state or state.freeze_tokens <= 0
                        else "Complete one speaking challenge today or use a freeze token to protect your streak."
                    ),
                    href="/speaking",
                    priority="urgent",
                    created_at=now,
                    session_id=None,
                )
            )
        else:
            notifications.append(
                NotificationItemResponse(
                    id=f"practice-reminder-{user_id}-{today.isoformat()}",
                    type="practice_reminder",
                    title="Daily practice reminder",
                    body="Finish today's missions to build your Confidence habit.",
                    href="/dashboard",
                    priority="normal",
                    created_at=now,
                    session_id=None,
                )
            )
        return notifications

    @staticmethod
    def _priority_rank(priority: str) -> int:
        return {"urgent": 2, "normal": 1}.get(priority, 0)

    @staticmethod
    def _aware(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
