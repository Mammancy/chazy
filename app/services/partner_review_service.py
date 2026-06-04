from __future__ import annotations

from collections import Counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.partner_review import PartnerReview
from app.models.practice_session import PracticeSession
from app.models.user import User
from app.schemas.partner_review import (
    PartnerReputationResponse,
    PartnerReviewCreate,
    PartnerReviewListResponse,
    PartnerReviewResponse,
    PartnerReviewReviewer,
)


class PartnerReviewService:
    def __init__(self, db: Session):
        self.db = db

    def create_review(
        self,
        *,
        session_id: int,
        reviewer: User,
        payload: PartnerReviewCreate,
    ) -> PartnerReviewResponse:
        session = self.db.get(PracticeSession, session_id)
        if session is None:
            raise ValueError("Practice session not found.")
        if reviewer.id not in {session.requester_user_id, session.partner_user_id}:
            raise PermissionError("Only session participants may review a speaking partner.")
        if session.status != "completed":
            raise ValueError("Practice sessions can only be reviewed after completion.")

        reviewed_user_id = (
            session.partner_user_id
            if reviewer.id == session.requester_user_id
            else session.requester_user_id
        )
        existing = self.db.scalar(
            select(PartnerReview).where(
                PartnerReview.session_id == session.id,
                PartnerReview.reviewer_id == reviewer.id,
            )
        )
        if existing is not None:
            raise ValueError("You have already reviewed this practice session.")

        review = PartnerReview(
            session_id=session.id,
            reviewer_id=reviewer.id,
            reviewed_user_id=reviewed_user_id,
            rating=payload.rating,
            comment=payload.comment.strip(),
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return self._review_response(review)

    def list_reviews(self, *, user_id: int) -> PartnerReviewListResponse:
        reviews = self.db.scalars(
            select(PartnerReview)
            .where(PartnerReview.reviewed_user_id == user_id)
            .order_by(PartnerReview.created_at.desc(), PartnerReview.id.desc())
        ).all()
        return PartnerReviewListResponse(reviews=[self._review_response(review) for review in reviews])

    def reputation(self, *, user_id: int) -> PartnerReputationResponse:
        reviews = self.db.scalars(
            select(PartnerReview)
            .where(PartnerReview.reviewed_user_id == user_id)
            .order_by(PartnerReview.created_at.desc(), PartnerReview.id.desc())
        ).all()
        completed_sessions = self._completed_sessions(user_id=user_id)
        average_rating = round(sum(review.rating for review in reviews) / len(reviews), 1) if reviews else 0.0
        return PartnerReputationResponse(
            average_rating=average_rating,
            total_reviews=len(reviews),
            completed_sessions=len(completed_sessions),
            reliability_score=self._reliability_score(user_id=user_id),
            repeat_partner_count=self._repeat_partner_count(user_id=user_id, sessions=completed_sessions),
            recent_reviews=[self._review_response(review) for review in reviews[:3]],
        )

    def _completed_sessions(self, *, user_id: int) -> list[PracticeSession]:
        return self.db.scalars(
            select(PracticeSession).where(
                PracticeSession.status == "completed",
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
            )
        ).all()

    def _reliability_score(self, *, user_id: int) -> int:
        total = self.db.scalar(
            select(func.count(PracticeSession.id)).where(
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
                PracticeSession.status.in_(["completed", "cancelled", "missed"]),
            )
        ) or 0
        if total == 0:
            return 0
        completed = self.db.scalar(
            select(func.count(PracticeSession.id)).where(
                or_(PracticeSession.requester_user_id == user_id, PracticeSession.partner_user_id == user_id),
                PracticeSession.status == "completed",
            )
        ) or 0
        return round((completed / total) * 100)

    @staticmethod
    def _repeat_partner_count(*, user_id: int, sessions: list[PracticeSession]) -> int:
        partners = Counter(
            session.partner_user_id if session.requester_user_id == user_id else session.requester_user_id
            for session in sessions
        )
        return sum(1 for count in partners.values() if count >= 2)

    def _review_response(self, review: PartnerReview) -> PartnerReviewResponse:
        return PartnerReviewResponse(
            id=review.id,
            session_id=review.session_id,
            reviewer_id=review.reviewer_id,
            reviewed_user_id=review.reviewed_user_id,
            rating=review.rating,
            comment=review.comment or "",
            reviewer=self._reviewer(review.reviewer_id),
            created_at=review.created_at,
        )

    def _reviewer(self, user_id: int) -> PartnerReviewReviewer:
        user = self.db.get(User, user_id)
        display_name = user.full_name if user and user.full_name else "Confidence Learner"
        return PartnerReviewReviewer(
            id=user_id,
            display_name=display_name,
            initials=self._initials(display_name),
        )

    @staticmethod
    def _initials(name: str) -> str:
        parts = [part[0] for part in name.split() if part]
        return "".join(parts[:2]).upper() or "CL"
