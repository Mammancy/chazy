from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.admin_auth import get_admin_user, require_admin_csrf
from app.models.user import User
from app.schemas.admin_users import (
    AdminCreateRequest,
    AdminUserListResponse,
    AdminUserProfileResponse,
    AdminUserStatusResponse,
    AdminUserStatusUpdate,
)
from app.schemas.user import BasicResponse
from app.services.admin_user_service import AdminUserService
from app.services.admin_audit_service import AdminAuditService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/", response_model=AdminUserListResponse)
def list_admin_users(
    search: str | None = Query(default=None),
    status: str = Query(default="all", pattern="^(all|active|inactive)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    return AdminUserService(db).list_users(search=search, status=status, limit=limit, offset=offset)


@router.post("/admins", response_model=AdminUserStatusResponse)
def create_admin_user(
    payload: AdminCreateRequest,
    request: Request,
    current_admin: User = Depends(get_admin_user),
    csrf: None = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> AdminUserStatusResponse:
    result = AdminUserService(db).create_admin(payload)
    AdminAuditService(db).log(
        admin_user=current_admin,
        action="admin_user_created",
        request=request,
        target_type="user",
        target_id=result.user.id,
        metadata={"email": result.user.email, "role": "admin"},
    )
    return result


@router.get("/{user_id}", response_model=AdminUserProfileResponse)
def get_admin_user_profile(
    user_id: int,
    current_admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserProfileResponse:
    try:
        return AdminUserService(db).get_profile(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{user_id}/status", response_model=AdminUserStatusResponse)
def update_admin_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    request: Request,
    current_admin: User = Depends(get_admin_user),
    csrf: None = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> AdminUserStatusResponse:
    try:
        if payload.is_active is None and payload.public_profile_visible is None:
            raise HTTPException(status_code=422, detail="At least one status field is required.")
        result = AdminUserService(db).update_status(
            user_id,
            is_active=payload.is_active,
            public_profile_visible=payload.public_profile_visible,
        )
        AdminAuditService(db).log(
            admin_user=current_admin,
            action="admin_user_status_updated",
            request=request,
            target_type="user",
            target_id=user_id,
            metadata={
                "is_active": payload.is_active,
                "public_profile_visible": payload.public_profile_visible,
            },
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{user_id}", response_model=AdminUserStatusResponse)
def delete_admin_user(
    user_id: int,
    request: Request,
    current_admin: User = Depends(get_admin_user),
    csrf: None = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> AdminUserStatusResponse:
    if user_id == current_admin.id:
        raise HTTPException(status_code=403, detail="Administrators cannot delete their own account.")
    try:
        result = AdminUserService(db).delete_user(user_id)
        AdminAuditService(db).log(
            admin_user=current_admin,
            action="admin_user_deleted",
            request=request,
            target_type="user",
            target_id=user_id,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{user_id}/purge", response_model=BasicResponse)
def purge_admin_user(
    user_id: int,
    request: Request,
    current_admin: User = Depends(get_admin_user),
    csrf: None = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> BasicResponse:
    if user_id == current_admin.id:
        raise HTTPException(status_code=403, detail="Administrators cannot purge their own account.")
    try:
        AdminUserService(db).purge_user(user_id)
        AdminAuditService(db).log(
            admin_user=current_admin,
            action="admin_user_purged",
            request=request,
            target_type="user",
            target_id=user_id,
        )
        return BasicResponse(success=True, message="User permanently removed")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
