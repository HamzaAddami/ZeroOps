from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.core.db import get_db
from app.core.dependecies import authorize_project, authorize
from app.model.pipeline import Pipeline, PipelineStage, PipelineStatus, StageType, StageStatus
from app.model.project import Project
from app.model.user import User
from app.service.pipeline_service import PipelineRunner

pipeline_router = APIRouter(prefix="/pipelines", tags=["Pipelines"])



class StageResponse(BaseModel):
    id: UUID
    order: int
    type: str
    status: str
    logs: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PipelineResponse(BaseModel):
    id: UUID
    project_id: UUID
    commit_sha: str
    commit_message: Optional[str] = None
    branch: str
    status: str
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None  # Fix: Remplacement de str par datetime
    finished_at: Optional[datetime] = None  # Fix: Remplacement de str par datetime
    stages: List[StageResponse] = []
    created_at: datetime  # Fix: Remplacement de str par datetime

    class Config:
        from_attributes = True



@pipeline_router.get("/project/{project_id}", response_model=List[PipelineResponse])
async def list_pipelines(
        project_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize_project("project_id"))
):
    return (
        db.query(Pipeline)
        .filter(project_id == Pipeline.project_id)
        .order_by(Pipeline.created_at.desc())
        .limit(20)
        .all()
    )


@pipeline_router.get("/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
        pipeline_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize)
):
    pipeline = db.query(Pipeline).filter(pipeline_id == Pipeline.id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    project = db.query(Project).filter(Project.id == pipeline.project_id, Project.is_deleted == False).first()
    if not project:
        raise HTTPException(403, "Access denied to this pipeline's project resource")

    return pipeline


@pipeline_router.post("/{pipeline_id}/cancel")
async def cancel_pipeline(
        pipeline_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize)
):
    pipeline = db.query(Pipeline).filter(pipeline_id == Pipeline.id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    project = db.query(Project).filter(Project.id == pipeline.project_id, Project.is_deleted == False).first()
    if not project:
        raise HTTPException(403, "Access denied to change this pipeline state")

    if pipeline.status in [PipelineStatus.failed, PipelineStatus.success, "cancelled"]:
        raise HTTPException(400, f"Pipeline execution sequence already completed: {pipeline.status}")

    pipeline.status = PipelineStatus.failed
    pipeline.finished_at = datetime.utcnow()

    for stage in pipeline.stages:
        if stage.status == StageStatus.pending or stage.status == "running":
            stage.status = "failed"
            stage.error_message = "Pipeline operation cancelled by user directive"
            stage.finished_at = datetime.utcnow()

    project.status = "failed"
    db.commit()
    return {"message": "Pipeline run cancellation successfully handled", "pipeline_id": str(pipeline_id)}


@pipeline_router.post("/project/{project_id}/trigger", response_model=dict)
async def trigger_pipeline_manual(
        project_id: UUID,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(authorize_project("project_id"))
):

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False
    ).first()

    if not project:
        raise HTTPException(404, "Project context lookup failed")
    if not project.last_commit_sha:
        raise HTTPException(400, "No active deployment history found. Push source artifacts to repository first")

    pipeline = Pipeline(
        project_id=project_id,
        triggered_by_id=current_user.id,
        commit_sha=project.last_commit_sha,
        commit_message="Manual zeroOps dashboard override invocation",
        branch=project.branch or "main",
    )
    db.add(pipeline)
    db.flush()

    stage_order = [
        StageType.source_checkout,
        StageType.code_analysis,
        StageType.unit_tests,
        StageType.build,
        StageType.security_scan,
        StageType.push_registry,
        StageType.deploy,
    ]

    for i, st in enumerate(stage_order, start=1):
        db.add(PipelineStage(
            pipeline_id=pipeline.id,
            order=i,
            type=st,
            status=StageStatus.pending
        ))

    project.status = "building"
    db.commit()

    background_tasks.add_task(PipelineRunner.run, str(pipeline.id))

    return {"pipeline_id": str(pipeline.id), "status": "triggered"}