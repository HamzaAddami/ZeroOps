from fastapi import APIRouter, status
from fastapi.params import Depends
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.dependecies import authorize
from app.dto.projectDTO import ProjectResponse, ProjectCreate
from app.service.project_service import ProjectService
from app.model.user import User
project_router = APIRouter(prefix="/projects", tags=["Projects"])

@project_router.get("/", response_model=List[ProjectResponse])
def list_projects(
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize)
):
    return ProjectService.get_all_projects(db)

@project_router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
        project: ProjectCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize)
):
    return ProjectService.create_project(db, project, current_user)

@project_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
        project_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize)
):
    return ProjectService.get_project_by_id(db, project_id)

@project_router.get("/{project_name}", response_model=ProjectResponse)
def get_project_by_name(
        project_name: str,
        db: Session = Depends(get_db)
):
    return ProjectService.get_project_by_name(db, project_name)




