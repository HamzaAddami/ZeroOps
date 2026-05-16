from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependecies import get_current_user, get_mfa_pending_user
from app.model.user import User
from app.service.user_service import UserService
from app.dto.user_dto import (
    UserChangePassword,
    MFAVerifyRequest,
    MFAConfirmRequest,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme_raw = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")



@auth_router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    return UserService.login_user(db, form_data.username, form_data.password)

@auth_router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme_raw),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return UserService.logout_user(db, token)


@auth_router.post("/change-password")
def change_password(
    data: UserChangePassword,
    db: Session = Depends(get_db),
    user: User = Depends(get_mfa_pending_user)
):
    return UserService.change_password(
        db, user,
        data.old_password,
        data.new_password,
        data.confirm_password
    )


@auth_router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@auth_router.post("/mfa/setup")
def setup_mfa(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return UserService.setup_mfa(db, current_user)


@auth_router.post("/mfa/confirm")
def confirm_mfa(
    data: MFAConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return UserService.confirm_mfa(db, current_user, data.code)


@auth_router.post("/mfa/verify")
def verify_mfa(
    data: MFAVerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_mfa_pending_user)
):
    return UserService.verify_mfa(db, user, data.code)


@auth_router.post("/mfa/disable")
def disable_mfa(
    data: MFAConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return UserService.disable_mfa(db, current_user, data.code)

