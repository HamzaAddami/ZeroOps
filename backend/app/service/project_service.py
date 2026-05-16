from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Type
from app.model.project import Project
from app.model.user import User
from app.dto.projectDTO import ProjectCreate, ProjectUpdate
from uuid import UUID
from app.service.user_service import UserService


class ProjectService:

    @staticmethod
    def get_all_projects(db: Session) -> list[Type[Project]]:
        projects = db.query(Project).all()
        if not projects:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No projects found",
            )
        return projects

    @staticmethod
    def get_project_by_id(db: Session, project_id: UUID) -> Type[Project]:
        project = db.query(Project).filter(
            project_id == Project.id,
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not in database"
            )
        return project

    @staticmethod
    def find_project_by_id(db: Session, project_id: UUID) -> Type[Project]:
        return db.query(Project).filter(project_id == Project.id).first()

    @staticmethod
    def get_project_by_name(db: Session, project_name: str) -> Type[Project]:
        project = db.query(Project).filter(project_name == Project.name).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not in database"
            )
        return project

    @staticmethod
    def find_project_by_name(db: Session, project_name: str) -> Type[Project]:
        return db.query(Project).filter(project_name == Project.name).first()

    @staticmethod
    def create_project(db: Session, project_data: ProjectCreate, user: User) -> Project:
        project = ProjectService.find_project_by_id(db, project_data.id)
        if project:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Project '{project_data.name}' already exists"
            )

        new_project = Project(**project_data.model_dump())
        new_project.members.append(user)
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        return new_project

    @staticmethod
    def update_project(db: Session, project_id: UUID, project_data: ProjectUpdate) -> Type[Project]:
        project = ProjectService.find_project_by_id(db, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_data.name}' not in database"
            )

        for field, value in project_data.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def delete_project(db: Session, project_id: UUID) -> dict:
        project = ProjectService.find_project_by_id(db, project_id)
        project.soft_delete()
        db.commit()
        return {"message": f'Project {project.name}deleted'}


    # Project Members

    @staticmethod
    def add_member(db: Session, project_id: UUID, user: User) -> dict:
        project = ProjectService.find_project_by_id(db, project_id)
        member = UserService.find_user_by_id(db, user.id)

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user.full_name}' not in database"
            )

        if member in project.members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User '{user.full_name}' already member this project"
            )

        project.members.append(member)
        db.commit()
        return {"message": f'Member {project.name} added to '}

    @staticmethod
    def remove_member(db: Session, project_id: UUID, user: User) -> dict:
        project = ProjectService.find_project_by_id(db, project_id)
        member = UserService.find_user_by_id(db, user.id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user.full_name}' not in database"
            )

        project.members.remove(member)
        db.commit()
        return {"message": f'Member {project.name} removed from this project named "{project.name}"'}



