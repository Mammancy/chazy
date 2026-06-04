from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_self
from app.models.user import User
from app.schemas.user import (
    ActiveSessionListResponse,
    ActiveSessionResponse,
    AuthResponse,
    BasicResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    ResponseLengthPreferenceUpdate,
    SignInRequest,
    SignUpRequest,
    TokenResponse,
    UserRead,
)
from app.services.auth_service import AuthService
from app.services.refresh_token_service import RefreshTokenReuseError, RefreshTokenService
from app.services.token_service import TokenError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_up(payload)
    return _auth_response(db, user, "Account created successfully.")


@router.post("/signin", response_model=AuthResponse)
def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_in(payload)
    return _auth_response(db, user, "Signed in successfully.")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        tokens = RefreshTokenService(db).rotate(payload.refresh_token)
    except RefreshTokenReuseError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected.") from exc
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.") from exc
    return TokenResponse(**tokens.__dict__)


@router.post("/forgot-password", response_model=BasicResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).forgot_password(payload)
    return BasicResponse(success=True, message="If this email exists, password reset instructions have been sent.")


@router.post("/reset-password", response_model=BasicResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).reset_password(payload)
    return BasicResponse(success=True, message="Password reset successfully.")


@router.post("/change-password", response_model=BasicResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BasicResponse:
    AuthService(db).change_password(
        user_id=current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return BasicResponse(success=True, message="Password changed. Please sign in again.")


@router.get("/sessions", response_model=ActiveSessionListResponse)
def active_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActiveSessionListResponse:
    sessions = RefreshTokenService(db).list_active_for_user(current_user.id)
    return ActiveSessionListResponse(
        sessions=[
            ActiveSessionResponse(
                id=session.id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
            for session in sessions
        ]
    )


@router.post("/logout-all", response_model=BasicResponse)
def logout_all_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BasicResponse:
    RefreshTokenService(db).revoke_all_for_user(current_user.id)
    return BasicResponse(success=True, message="All sessions have been signed out.")


@router.get("/profile/{user_id}", response_model=UserRead)
def get_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    require_self(user_id, current_user)
    user = AuthService(db).get_profile(user_id)
    return UserRead.model_validate(user)


@router.patch("/profile/{user_id}/response-length", response_model=UserRead)
def update_response_length_preference(
    user_id: int,
    payload: ResponseLengthPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    require_self(user_id, current_user)
    user = AuthService(db).update_response_length_preference(user_id, payload.response_length_preference)
    return UserRead.model_validate(user)


@router.patch("/profile/{user_id}", response_model=UserRead)
def update_profile(
    user_id: int,
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    require_self(user_id, current_user)
    user = AuthService(db).update_profile(user_id, payload)
    return UserRead.model_validate(user)


@router.delete("/profile/{user_id}", response_model=BasicResponse)
def delete_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BasicResponse:
    require_self(user_id, current_user)
    AuthService(db).delete_account(user_id)
    return BasicResponse(success=True, message="Account deleted successfully.")


def _auth_response(db: Session, user: User, message: str) -> AuthResponse:
    tokens = RefreshTokenService(db).issue_pair(user)
    return AuthResponse(
        success=True,
        message=message,
        user=UserRead.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )
