from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.user import (
    AuthResponse,
    BasicResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResponseLengthPreferenceUpdate,
    SignInRequest,
    SignUpRequest,
    UserRead,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_up(payload)
    return AuthResponse(success=True, message="Account created successfully.", user=UserRead.model_validate(user))


@router.post("/signin", response_model=AuthResponse)
def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).sign_in(payload)
    return AuthResponse(success=True, message="Signed in successfully.", user=UserRead.model_validate(user))


@router.post("/forgot-password", response_model=BasicResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).forgot_password(payload)
    return BasicResponse(success=True, message="If this email exists, password reset instructions have been sent.")


@router.post("/reset-password", response_model=BasicResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).reset_password(payload)
    return BasicResponse(success=True, message="Password reset successfully.")


@router.get("/profile/{user_id}", response_model=UserRead)
def get_profile(user_id: int, db: Session = Depends(get_db)) -> UserRead:
    user = AuthService(db).get_profile(user_id)
    return UserRead.model_validate(user)


@router.patch("/profile/{user_id}/response-length", response_model=UserRead)
def update_response_length_preference(
    user_id: int,
    payload: ResponseLengthPreferenceUpdate,
    db: Session = Depends(get_db),
) -> UserRead:
    user = AuthService(db).update_response_length_preference(user_id, payload.response_length_preference)
    return UserRead.model_validate(user)




@router.delete("/profile/{user_id}", response_model=BasicResponse)
def delete_profile(user_id: int, db: Session = Depends(get_db)) -> BasicResponse:
    AuthService(db).delete_account(user_id)
    return BasicResponse(success=True, message="Account deleted successfully.")

