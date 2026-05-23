from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.admin_users import (
    AdminUserListResponse,
    AdminUserProfileResponse,
    AdminUserStatusResponse,
    AdminUserStatusUpdate,
)
from app.services.admin_user_service import AdminUserService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/", response_model=AdminUserListResponse)
async def list_admin_users(
    search: str | None = Query(default=None),
    status: str = Query(default="all", pattern="^(all|active|inactive)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    return AdminUserService(db).list_users(search=search, status=status, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=AdminUserProfileResponse)
async def get_admin_user_profile(user_id: int, db: Session = Depends(get_db)) -> AdminUserProfileResponse:
    try:
        return AdminUserService(db).get_profile(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{user_id}/status", response_model=AdminUserStatusResponse)
async def update_admin_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    db: Session = Depends(get_db),
) -> AdminUserStatusResponse:
    try:
        return AdminUserService(db).update_status(user_id, payload.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{user_id}", response_model=AdminUserStatusResponse)
async def delete_admin_user(user_id: int, db: Session = Depends(get_db)) -> AdminUserStatusResponse:
    try:
        return AdminUserService(db).delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
