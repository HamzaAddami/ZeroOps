
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID
import re
from app.model.project import Project
from app.model.user import User
from app.dto.project_dto import ProjectCreate, ProjectUpdate
from app.service.github_app_service import get_repo_id, add_repo_to_app_installation


class ProjectService:

    @staticmethod
    def _get_or_404(db: Session, project_id: UUID) -> Project:
        project = db.query(Project).filter(
            project_id == Project.id,
            Project.is_deleted == False
        ).first()
        if not project:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Project not found"
            )
        return project


    @staticmethod
    def get_all_projects(db: Session, user: User) -> list:

        query = db.query(Project).filter(Project.is_deleted == False)

        if user.role.value in ("admin", "manager"):
            return query.order_by(Project.created_at.desc()).all()

        return (
            query
            .filter(Project.members.any(User.id == user.id))
            .order_by(Project.created_at.desc())
            .all()
        )

    @staticmethod
    def get_project_by_id(db: Session, project_id: UUID) -> Project:
        return ProjectService._get_or_404(db, project_id)

    @staticmethod
    def get_project_by_name(db: Session, name: str) -> Project:
        project = db.query(Project).filter(
            name == Project.name,
            Project.is_deleted == False
        ).first()
        if not project:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Project '{name}' not found"
            )
        return project

    @staticmethod
    def _parse_repo_info(repository_url: str) -> tuple[str, str] | None:
        pattern = r"github\.com[/:]([^/]+)/([^/\.]+)"
        match = re.search(pattern, repository_url or "")
        if match:
            return match.group(1), match.group(2)
        return None

    @staticmethod
    async def create_project(
            db: Session,
            data: ProjectCreate,
            user: User
    ) -> Project:
        existing = db.query(Project).filter(
            data.name == Project.name
        ).first()
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Project name '{data.name}' already taken"
            )

        project = Project(
            name=data.name,
            description=data.description,
            repository_url=data.repository_url,
            branch=data.branch or "main",
        )
        project.members.append(user)
        db.add(project)
        db.commit()
        db.refresh(project)

        if data.repository_url:
            repo_info = ProjectService._parse_repo_info(data.repository_url)
            if repo_info:
                repo_owner, repo_name = repo_info
                repo_id = await get_repo_id(repo_owner, repo_name)
                if repo_id:
                    await add_repo_to_app_installation(repo_id)

        return project

    @staticmethod
    def update_project(
        db: Session,
        project_id: UUID,
        data: ProjectUpdate
    ) -> Project:
        project = ProjectService._get_or_404(db, project_id)

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(project, field, value)

        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def delete_project(db: Session, project_id: UUID) -> dict:
        project = ProjectService._get_or_404(db, project_id)
        project.soft_delete()
        db.commit()
        return {"message": f"Project '{project.name}' deleted"}

    # Members

    @staticmethod
    def add_member(db: Session, project_id: UUID, user_id: UUID) -> dict:
        project = ProjectService._get_or_404(db, project_id)
        member  = db.query(User).filter(user_id == User.id).first()

        if not member:
            raise HTTPException(404, "User not found")

        if member in project.members:
            raise HTTPException(409, "User already a member")

        project.members.append(member)
        db.commit()
        return {"message": f"{member.username} added to project"}

    @staticmethod
    def remove_member(db: Session, project_id: UUID, user_id: UUID) -> dict:
        project = ProjectService._get_or_404(db, project_id)
        member  = db.query(User).filter(user_id == User.id).first()

        if not member or member not in project.members:
            raise HTTPException(404, "Member not found in project")

        project.members.remove(member)
        db.commit()
        return {"message": f"{member.username} removed from project"}