from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementAward
from app.models.practice_session import PracticeSession
from app.models.speaking_partner import PracticeRequest
from app.models.user import User
from app.schemas.practice_session import (
    PracticeSessionCreate,
    PracticeSessionFeedback,
    PracticeSessionListResponse,
    PracticeSessionResponse,
    PracticeSessionUpdate,
    PracticeSessionUserSummary,
)
from app.services.achievement_service import AchievementService


class PracticeSessionService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user: User, payload: PracticeSessionCreate) -> PracticeSessionResponse:
        request = self.db.get(PracticeRequest, payload.request_id)
        if request is None:
            raise ValueError("Practice request not found.")
        if request.status != "accepted":
            raise ValueError("Only accepted practice requests can create practice sessions.")
        if user.id not in {request.sender_user_id, request.receiver_user_id}:
            raise PermissionError("Only request participants can schedule this practice session.")

        session = PracticeSession(
            requester_user_id=request.sender_user_id,
            partner_user_id=request.receiver_user_id,
            request_id=request.id,
            scheduled_at=payload.scheduled_at,
            duration_minutes=payload.duration_minutes,
            topic=payload.topic.strip(),
            notes=payload.notes.strip(),
            status="scheduled",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return self._response(session)

    def list(self, *, user_id: int) -> PracticeSessionListResponse:
        sessions = self.db.scalars(
            select(PracticeSession)
            .where(or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id))
            .order_by(PracticeSession.scheduled_at.asc())
        ).all()
        return PracticeSessionListResponse(sessions=[self._response(session) for session in sessions])

    def get(self, *, session_id: int, user_id: int) -> PracticeSessionResponse:
        session = self._authorized_session(session_id=session_id, user_id=user_id)
        return self._response(session)

    def update(self, *, session_id: int, user_id: int, payload: PracticeSessionUpdate) -> PracticeSessionResponse:
        session = self._authorized_session(session_id=session_id, user_id=user_id)
        if session.status == "completed":
            raise ValueError("Completed practice sessions cannot be rescheduled.")
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if value is None:
                continue
            if field in {"topic", "notes"} and isinstance(value, str):
                value = value.strip()
            setattr(session, field, value)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return self._response(session)

    def complete(
        self,
        *,
        session_id: int,
        user: User,
        payload: PracticeSessionFeedback,
    ) -> PracticeSessionResponse:
        session = self._authorized_session(session_id=session_id, user_id=user.id)
        if session.status == "cancelled":
            raise ValueError("Cancelled practice sessions cannot be completed.")
        session.status = "completed"
        self._set_feedback(session, user.id, payload.feedback.strip())
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        self._award_completion_xp(session)
        return self._response(session)

    def cancel(self, *, session_id: int, user_id: int) -> PracticeSessionResponse:
        session = self._authorized_session(session_id=session_id, user_id=user_id)
        if session.status == "completed":
            raise ValueError("Completed practice sessions cannot be cancelled.")
        session.status = "cancelled"
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return self._response(session)

    def completed_count(self, *, user_id: int) -> int:
        return self.db.query(PracticeSession).filter(
            PracticeSession.status == "completed",
            or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
        ).count()

    def _authorized_session(self, *, session_id: int, user_id: int) -> PracticeSession:
        session = self.db.get(PracticeSession, session_id)
        if session is None:
            raise ValueError("Practice session not found.")
        if user_id not in {session.requester_user_id, session.partner_user_id}:
            raise PermissionError("Only session participants can access this practice session.")
        return session

    def _set_feedback(self, session: PracticeSession, user_id: int, feedback: str) -> None:
        if user_id == session.requester_user_id:
            session.feedback_requester = feedback
        elif user_id == session.partner_user_id:
            session.feedback_partner = feedback

    def _award_completion_xp(self, session: PracticeSession) -> None:
        points = self._xp_for_duration(session.duration_minutes)
        for user_id in {session.requester_user_id, session.partner_user_id}:
            session_id = f"chazy-user-{user_id}"
            achievement_key = f"practice_session_{session.id}_xp"
            exists = self.db.scalar(
                select(AchievementAward).where(
                    AchievementAward.user_id == user_id,
                    AchievementAward.achievement_key == achievement_key,
                )
            )
            if exists is None:
                self.db.add(
                    AchievementAward(
                        session_id=session_id,
                        user_id=user_id,
                        achievement_key=achievement_key,
                        category="practice_session",
                        title="Practice Session Complete",
                        description="Completed a scheduled human speaking practice session.",
                        points=points,
                        metadata_json={
                            "practice_session_id": session.id,
                            "duration_minutes": session.duration_minutes,
                        },
                    )
                )
        self.db.commit()
        for user_id in {session.requester_user_id, session.partner_user_id}:
            AchievementService(self.db).evaluate(session_id=f"chazy-user-{user_id}", user_id=user_id)

    @staticmethod
    def _xp_for_duration(duration_minutes: int) -> int:
        if duration_minutes >= 60:
            return 80
        if duration_minutes >= 30:
            return 40
        return 20

    def _response(self, session: PracticeSession) -> PracticeSessionResponse:
        return PracticeSessionResponse(
            id=session.id,
            requester_user_id=session.requester_user_id,
            partner_user_id=session.partner_user_id,
            request_id=session.request_id,
            scheduled_at=session.scheduled_at,
            duration_minutes=session.duration_minutes,
            topic=session.topic or "",
            notes=session.notes or "",
            status=session.status,
            feedback_requester=session.feedback_requester or "",
            feedback_partner=session.feedback_partner or "",
            requester=self._user_summary(session.requester_user_id),
            partner=self._user_summary(session.partner_user_id),
            xp_awarded=self._xp_for_duration(session.duration_minutes) if session.status == "completed" else 0,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _user_summary(self, user_id: int) -> PracticeSessionUserSummary:
        user = self.db.get(User, user_id)
        display_name = user.full_name if user and user.full_name else "Confidence Learner"
        return PracticeSessionUserSummary(
            id=user_id,
            display_name=display_name,
            initials=self._initials(display_name),
        )

    @staticmethod
    def _initials(name: str) -> str:
        return "".join(part[0] for part in name.split() if part)[:2].upper() or "CL"
