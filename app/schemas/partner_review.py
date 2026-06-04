from datetime import datetime

from pydantic import BaseModel, Field


class PartnerReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class PartnerReviewReviewer(BaseModel):
    id: int
    display_name: str
    initials: str


class PartnerReviewResponse(BaseModel):
    id: int
    session_id: int
    reviewer_id: int
    reviewed_user_id: int
    rating: int
    comment: str
    reviewer: PartnerReviewReviewer
    created_at: datetime


class PartnerReviewListResponse(BaseModel):
    reviews: list[PartnerReviewResponse]


class PartnerReputationResponse(BaseModel):
    average_rating: float
    total_reviews: int
    completed_sessions: int
    reliability_score: int
    repeat_partner_count: int
    recent_reviews: list[PartnerReviewResponse]
