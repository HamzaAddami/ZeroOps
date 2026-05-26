# app/api/routes/project_router.py
from fastapi import APIRouter, status, Depends
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependecies import authorize, authorize_project
from app.dto.project_dto import ProjectCreate, ProjectUpdate, ProjectResponse, MemberAdd
from app.service.project_service import ProjectService
from app.model.user import User

project_router = APIRouter(prefix="/projects", tags=["Projects"])


@project_router.get("/", response_model=List[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return ProjectService.get_all_projects(db, current_user)


@project_router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED
)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return ProjectService.create_project(db, data, current_user)


@project_router.get("/by-name/{project_name}", response_model=ProjectResponse)
def get_project_by_name(
    project_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return ProjectService.get_project_by_name(db, project_name)


@project_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):
    return ProjectService.get_project_by_id(db, project_id)


@project_router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):
    return ProjectService.update_project(db, project_id, data)


@project_router.delete("/{project_id}")
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):
    return ProjectService.delete_project(db, project_id)


@project_router.post("/{project_id}/members/{member_id}")
def add_member(
    project_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):
    return ProjectService.add_member(db, project_id, member_id)


@project_router.delete("/{project_id}/members/{member_id}")
def remove_member(
    project_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):
    return ProjectService.remove_member(db, project_id, member_id)