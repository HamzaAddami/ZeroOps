from sqlalchemy.orm import Session
from fastapi import HTTPException
from uuid import UUID
from datetime import datetime

from app.model.deployment import Deployment, DeploymentStatus
from app.model.project import Project


class DeploymentService:

    @staticmethod
    def _get_or_404(db: Session, deployment_id: UUID) -> Deployment:
        d = db.query(Deployment).filter(deployment_id == Deployment.id).first()
        if not d:
            raise HTTPException(404, "Deployment not found")
        return d

    @staticmethod
    def list_by_project(db: Session, project_id: UUID) -> list[Deployment]:
        return (
            db.query(Deployment)
            .filter(Deployment.project_id == project_id)
            .order_by(Deployment.created_at.desc())
            .limit(20)
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, deployment_id: UUID) -> Deployment:
        return DeploymentService._get_or_404(db, deployment_id)

    @staticmethod
    def get_latest_by_project(db: Session, project_id: UUID) -> Deployment:
        d = (
            db.query(Deployment)
            .filter(Deployment.project_id == project_id)
            .order_by(Deployment.created_at.desc())
            .first()
        )
        if not d:
            raise HTTPException(404, "No deployment found for this project")
        return d

    @staticmethod
    def update_status(
        db: Session,
        deployment_id: UUID,
        status: DeploymentStatus,
        replicas_ready: int = None,
        deployment_url: str = None,
    ) -> Deployment:

        d = DeploymentService._get_or_404(db, deployment_id)
        d.status = status

        if replicas_ready is not None:
            d.replicas_ready = replicas_ready

        if deployment_url:
            d.deployment_url = deployment_url

        if status == DeploymentStatus.running and not d.deployed_at:
            d.deployed_at = datetime.utcnow()

        if status in (DeploymentStatus.running, DeploymentStatus.failed,
                      DeploymentStatus.rolled_back) and d.deployed_at:
            d.duration_seconds = int(
                (datetime.utcnow() - d.deployed_at).total_seconds()
            )

        db.commit()
        db.refresh(d)
        return d

    @staticmethod
    def rollback(db: Session, deployment_id: UUID) -> Deployment:
        d = DeploymentService._get_or_404(db, deployment_id)
        if not d.previous_image_tag:
            raise HTTPException(400, "No previous image to roll back to")
        d.rollback()
        db.commit()
        db.refresh(d)
        return d