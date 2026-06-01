import hmac
import hashlib
import logging
import os
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.model.pipeline import Pipeline, PipelineStage, StageType, StageStatus
from app.model.project import Project
from app.service.pipeline_service import PipelineRunner

logger = logging.getLogger(__name__)
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return True
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@webhook_router.post("/github")
async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_github_signature(payload_bytes, signature):
        raise HTTPException(401, "Invalid webhook signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        return {"status": "ignored", "reason": f"Event '{event_type}' is unhandled"}

    payload = await request.json()
    ref = payload.get("ref", "")
    commit_sha = payload.get("after", "")
    repo = payload.get("repository", {})
    repo_name = repo.get("name", "")

    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

    if commit_sha == "0000000000000000000000000000000000000000":
        return {"status": "ignored", "reason": "Branch deletion payload"}

    # Recherche flexible basée sur le nom du dépôt
    project = db.query(Project).filter(
        Project.repository_url.ilike(f"%{repo_name}%"),
        Project.is_deleted == False
    ).first()

    if not project:
        return {"status": "ignored", "reason": f"No active project linked with repository name '{repo_name}'"}

    if project.branch and project.branch != branch:
        return {"status": "ignored", "reason": f"Branch tracking mismatch (Targeting: {project.branch})"}

    head_commit = payload.get("head_commit", {})
    commit_msg = head_commit.get("message", "Triggered via GitHub App push event")[
                 :255] if head_commit else "GitHub push event execution"

    # Initialisation de l'arborescence DB Pipeline
    pipeline = Pipeline(
        project_id=project.id, commit_sha=commit_sha,
        commit_message=commit_msg, branch=branch
    )
    db.add(pipeline)
    db.flush()

    stage_order = [
        StageType.source_checkout, StageType.code_analysis,
        StageType.unit_tests, StageType.build,
        StageType.security_scan, StageType.push_registry, StageType.deploy,
    ]

    for i, stage_type in enumerate(stage_order, start=1):
        db.add(PipelineStage(
            pipeline_id=pipeline.id, order=i, type=stage_type, status=StageStatus.pending
        ))

    project.last_commit_sha = commit_sha
    project.status = "building"
    db.commit()

    background_tasks.add_task(PipelineRunner.run, str(pipeline.id))
    return {"status": "accepted", "pipeline_id": str(pipeline.id), "project": project.name}


@webhook_router.get("/github/health")
async def webhook_health():
    return {"status": "ok", "secret_configured": bool(GITHUB_WEBHOOK_SECRET)}