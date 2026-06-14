from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from app.dto.deployment_dto import DeploymentResponse, StatusUpdateRequest
from app.core.db import get_db
from app.core.dependecies import authorize, authorize_project
from app.model.user import User
from app.service.deployment_service import DeploymentService

deployment_router = APIRouter(prefix="/deployments", tags=["Deployments"])


@deployment_router.get("/project/{project_id}", response_model=List[DeploymentResponse])
def list_deployments(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id")),
):
    return DeploymentService.list_by_project(db, project_id)


@deployment_router.get("/project/{project_id}/latest", response_model=DeploymentResponse)
def get_latest_deployment(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id")),
):
    return DeploymentService.get_latest_by_project(db, project_id)


@deployment_router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize),
):
    return DeploymentService.get_by_id(db, deployment_id)


@deployment_router.patch("/{deployment_id}/status", response_model=DeploymentResponse)
def update_deployment_status(
    deployment_id: UUID,
    body: StatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize),
):
    return DeploymentService.update_status(
        db, deployment_id,
        status=body.status,
        replicas_ready=body.replicas_ready,
        deployment_url=body.deployment_url,
    )


@deployment_router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
def rollback_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize),
):
    return DeploymentService.rollback(db, deployment_id)