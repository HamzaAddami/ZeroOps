from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.params import Depends
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.dto.projectDTO import ProjectResponse, ProjectCreate
from app.service import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.get("/", response_model=List[ProjectResponse])
def list_projects(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    return project_service.get_all_projects(db, skip=skip, limit=limit)

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
        project: ProjectCreate,
        db: Session = Depends(get_db)
):
    return project_service.create_project(db, project)

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
        project_id: UUID,
        db: Session = Depends(get_db)
):
    return project_service.get_project_by_id(db, project_id)

@router.get("/{project_name}", response_model=ProjectResponse)
def get_project_by_name(
        project_name: str,
        db: Session = Depends(get_db)
):
    return project_service.get_project_by_name(db, project_name)




