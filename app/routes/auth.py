from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user, require_self
from app.models.user import User
from app.schemas.user import (
    AuthResponse,
    BasicResponse,
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    ResponseLengthPreferenceUpdate,
    SignInRequest,
    SignUpRequest,
    TokenResponse,
    UserRead,
)
from app.services.auth_service import AuthService
from app.services.token_service import TokenError, TokenService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_up(payload)
    return _auth_response(user, "Account created successfully.")


@router.post("/signin", response_model=AuthResponse)
def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_in(payload)
    return _auth_response(user, "Signed in successfully.")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user_id = TokenService.decode_refresh_token(payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")

    tokens = TokenService.issue_pair(user)
    return TokenResponse(**tokens.__dict__)


@router.post("/forgot-password", response_model=BasicResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).forgot_password(payload)
    return BasicResponse(success=True, message="If this email exists, password reset instructions have been sent.")


@router.post("/reset-password", response_model=BasicResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).reset_password(payload)
    return BasicResponse(success=True, message="Password reset successfully.")


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


@router.delete("/profile/{user_id}", response_model=BasicResponse)
def delete_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BasicResponse:
    require_self(user_id, current_user)
    AuthService(db).delete_account(user_id)
    return BasicResponse(success=True, message="Account deleted successfully.")


def _auth_response(user: User, message: str) -> AuthResponse:
    tokens = TokenService.issue_pair(user)
    return AuthResponse(
        success=True,
        message=message,
        user=UserRead.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )
