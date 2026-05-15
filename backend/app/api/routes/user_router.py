from fastapi import APIRouter, status, HTTPException
from fastapi.params import Depends
from app.core.db import Session, get_db
from app.dto.user_dto import UserResponse, UserCreateByAdmin
from app.service.user_service import UserService

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/create", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_project(
        user: UserCreateByAdmin,
        db: Session = Depends(get_db())):
    return UserService.create_user_by_admin(db,user.full_name,user.email,user.password)

