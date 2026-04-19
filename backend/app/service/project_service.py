from fastapi import HTTPException, status
from sentry_sdk import continue_trace
from sqlalchemy.orm import Session
from typing import Type
from app.model.project import Project
from app.dto.projectDTO import ProjectCreate
from uuid import UUID


def get_all_projects(db: Session, skip: int = 0, limit: int = 100) -> list[Type[Project]]:
    projects = db.query(Project).offset(skip).limit(limit).all()
    if not projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No projects found",
        )
    return projects

def get_project_by_id(db: Session, project_id: UUID) -> Type[Project]:
    project = db.query(Project).filter(project_id == Project.id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not in database"
        )
    return project

def get_project_by_name(db: Session, project_name: str) -> Type[Project]:
    project = db.query(Project).filter(project_name == Project.name).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not in database"
        )
    return project

def find_project_by_name(db: Session, project_name: str) -> Type[Project]:
    return db.query(Project).filter(project_name == Project.name).first()

def create_project(db: Session, project_data: ProjectCreate) -> Project:
    existing = find_project_by_name(db, project_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project '{project_data.name}' already exists"
        )

    new_project = Project(**project_data.model_dump())

    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project
