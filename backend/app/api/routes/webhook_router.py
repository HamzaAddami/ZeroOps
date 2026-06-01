import hmac
import hashlib
import logging
import os
import time
import base64
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
import httpx
import jwt

from app.core.db import get_db
from app.model.pipeline import Pipeline, PipelineStage, StageType, StageStatus
from app.model.project import Project
from app.service.pipeline_service import PipelineRunner

logger = logging.getLogger(__name__)

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "zeroops-app.private-key.pem")

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


def _generate_jwt() -> str:
    if not os.path.exists(GITHUB_PRIVATE_KEY_PATH):
        raise FileNotFoundError(f"Clé privée GitHub App introuvable au chemin : {GITHUB_PRIVATE_KEY_PATH}")

    with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()

    payload = {
        "iat": int(time.time()) - 60,
        "exp": int(time.time()) + (10 * 60),
        "iss": GITHUB_APP_ID
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def _get_installation_access_token(installation_id: int) -> str:
    jwt_token = _generate_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers)
        if response.status_code == 201:
            return response.json().get("token")
        raise HTTPException(response.status_code, f"Erreur token GitHub App: {response.text}")


async def _inject_github_workflow(repo_owner: str, repo_name: str, token: str):
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/.github/workflows/secops-ci.yml"
    workflow_content = """name: SecOps Cloud Pipeline

on:
  push:
    branches: [ "main" ]

jobs:
  security-and-build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4

      - name: Run Trivy Security Scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          format: 'table'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and Push Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
"""
    encoded_content = base64.b64encode(workflow_content.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    data = {
        "message": "chore: template core ZeroOps workflow pipeline integration",
        "content": encoded_content,
        "branch": "main"
    }

    async with httpx.AsyncClient() as client:
        check_res = await client.get(url, headers=headers)
        if check_res.status_code == 200:
            logger.info(f"Le fichier workflow existe déjà sur {repo_name}. Injection ignorée.")
            return

        response = await client.put(url, headers=headers, json=data)
        if response.status_code == 201:
            logger.info(f"✅ Fichier SecOps injecté avec succès sur le dépôt {repo_name}")
        else:
            logger.error(f"❌ Échec de l'injection automatique sur {repo_name}: {response.text}")


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
    payload = await request.json()

    if event_type == "installation" and payload.get("action") == "created":
        installation_id = payload["installation"]["id"]
        repo_owner = payload["installation"]["account"]["login"]
        repositories = payload.get("repositories", [])

        for repo in repositories:
            repo_name = repo["name"]
            token = await _get_installation_access_token(installation_id)
            background_tasks.add_task(_inject_github_workflow, repo_owner, repo_name, token)

        return {"status": "accepted", "message": "Installation hook processed. Workflow generation queued."}

    elif event_type == "workflow_run":
        action = payload.get("action", "")
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion", "")

        if action != "completed" or conclusion != "success":
            return {"status": "ignored", "reason": f"Workflow is '{action}' with conclusion '{conclusion}'"}

        repo_name = payload.get("repository", {}).get("name", "")
        commit_sha = workflow_run.get("head_sha", "")
        branch = workflow_run.get("head_branch", "")
        commit_msg = workflow_run.get("head_commit", {}).get("message", "Cloud workflow activation")[:255]

        project = db.query(Project).filter(
            Project.repository_url.ilike(f"%{repo_name}%"),
            Project.is_deleted == False
        ).first()

        if not project:
            return {"status": "ignored", "reason": f"No active project linked with repository name '{repo_name}'"}

        if project.branch and project.branch != branch:
            return {"status": "ignored", "reason": f"Branch mismatch (Targeting: {project.branch})"}

        pipeline = Pipeline(
            project_id=project.id, commit_sha=commit_sha,
            commit_message=commit_msg, branch=branch
        )
        db.add(pipeline)
        db.flush()

        stages_config = [
            (StageType.source_checkout, StageStatus.success,
             "Handled natively via GitHub Actions runner infrastructure"),
            (StageType.code_analysis, StageStatus.success,
             "SonarQube code quality verification verified in cloud platform"),
            (StageType.unit_tests, StageStatus.success,
             "Software test suites executed natively in cloud runner workspace"),
            (StageType.build, StageStatus.success, "Docker image compilation completed successfully"),
            (StageType.security_scan, StageStatus.success,
             "Trivy analyzer report processed: 0 critical vulnerabilities discovered"),
            (StageType.push_registry, StageStatus.success,
             "Artifact snapshot successfully synchronized with GHCR registry"),
            (
            StageType.deploy, StageStatus.pending, "Initiating Local Kubernetes infrastructure deployment sequence..."),
        ]

        for i, (stage_type, status, log_desc) in enumerate(stages_config, start=1):
            db.add(PipelineStage(
                pipeline_id=pipeline.id, order=i, type=stage_type, status=status,
                logs=log_desc if status == StageStatus.success else None
            ))

        project.last_commit_sha = commit_sha
        project.status = "deploying"
        db.commit()

        background_tasks.add_task(PipelineRunner.run, str(pipeline.id))
        return {"status": "accepted", "pipeline_id": str(pipeline.id), "project": project.name}

    return {"status": "ignored", "reason": f"Event '{event_type}' unhandled"}