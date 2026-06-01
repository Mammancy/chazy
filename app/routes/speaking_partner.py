from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.speaking_partner import (
    PracticeRequestCreate,
    PracticeRequestListResponse,
    PracticeRequestResponse,
    PracticeRequestUpdate,
    RecommendedSpeakingPartnerListResponse,
    SpeakingPartnerListResponse,
    SpeakingPartnerProfileResponse,
    SpeakingPartnerProfileUpdate,
)
from app.services.speaking_partner_service import SpeakingPartnerService

router = APIRouter(prefix="/speaking-partners", tags=["speaking-partners"])


def _parse_interests(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("", response_model=SpeakingPartnerListResponse)
async def list_speaking_partners(
    speaking_level: str | None = None,
    native_language: str | None = None,
    target_language: str | None = None,
    interests: str | None = Query(default=None),
    timezone: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingPartnerListResponse:
    return SpeakingPartnerService(db).list_partners(
        current_user_id=current_user.id,
        speaking_level=speaking_level,
        native_language=native_language,
        target_language=target_language,
        interests=_parse_interests(interests),
        timezone=timezone,
    )


@router.get("/recommended", response_model=RecommendedSpeakingPartnerListResponse)
async def recommended_speaking_partners(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendedSpeakingPartnerListResponse:
    return SpeakingPartnerService(db).recommended_partners(current_user=current_user)


@router.get("/me", response_model=SpeakingPartnerProfileResponse)
async def get_my_speaking_partner_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingPartnerProfileResponse:
    return SpeakingPartnerService(db).my_profile(current_user)


@router.patch("/me", response_model=SpeakingPartnerProfileResponse)
async def update_my_speaking_partner_profile(
    payload: SpeakingPartnerProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingPartnerProfileResponse:
    return SpeakingPartnerService(db).update_my_profile(user=current_user, payload=payload)


@router.post("/requests", response_model=PracticeRequestResponse)
async def create_practice_request(
    payload: PracticeRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRequestResponse:
    try:
        return SpeakingPartnerService(db).create_request(sender=current_user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/requests", response_model=PracticeRequestListResponse)
async def list_practice_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRequestListResponse:
    return SpeakingPartnerService(db).list_requests(user_id=current_user.id)


@router.patch("/requests/{request_id}", response_model=PracticeRequestResponse)
async def update_practice_request(
    request_id: int,
    payload: PracticeRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeRequestResponse:
    try:
        return SpeakingPartnerService(db).update_request(
            request_id=request_id,
            user_id=current_user.id,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
