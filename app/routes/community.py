from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.community import CommunityFeedResponse, CommunityUsersResponse, PublicProfile
from app.services.community_service import CommunityService

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/feed", response_model=CommunityFeedResponse)
def get_community_feed(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CommunityFeedResponse:
    return CommunityService(db).get_feed(limit=limit, offset=offset)


@router.get("/users", response_model=CommunityUsersResponse)
def list_community_users(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CommunityUsersResponse:
    return CommunityService(db).list_users(limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=PublicProfile)
def get_public_profile(user_id: int, db: Session = Depends(get_db)) -> PublicProfile:
    try:
        return CommunityService(db).get_public_profile(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
