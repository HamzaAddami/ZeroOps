from typing import List
from uuid import UUID

from fastapi import APIRouter, status, HTTPException
from fastapi.params import Depends
from app.core.db import Session, get_db
from app.core.dependecies import require_admin
from app.dto.user_dto import UserResponse, UserCreateByAdmin, UserCreatedResponse, UpdateRoleRequest, BanRequest
from app.model.user import User
from app.service.user_service import UserService

user_router = APIRouter(prefix="/admin/users", tags=["Admin - Users"])


@user_router.get("/", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.get_all_users(db)


@user_router.post("/", response_model=UserCreatedResponse, status_code=201)
async def create_user(
    data: UserCreateByAdmin,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await UserService.create_user_by_admin(
        db, data.full_name, data.email, data.role, admin
    )
    return UserCreatedResponse(user=result["user"], temp_password=result["temp_password"])


@user_router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await UserService.get_user_by_id(db, user_id)
    return result


@user_router.post("/{user_id}/reset-password")
def reset_password(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.reset_password(db, user_id, admin)


@user_router.patch("/{user_id}/role", response_model=UserResponse)
def update_role(
    user_id: UUID,
    data: UpdateRoleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.update_role(db, user_id, data.role, admin)


@user_router.post("/{user_id}/activate", response_model=UserResponse)
def activate(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.activate_user(db, user_id)


@user_router.post("/{user_id}/ban", response_model=UserResponse)
def ban(
    user_id: UUID,
    data: BanRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.ban_user(db, user_id, data.reason, admin)


@user_router.post("/{user_id}/unlock", response_model=UserResponse)
def unlock(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.unlock_user(db, user_id)


@user_router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return UserService.delete_user(db, user_id, admin)

