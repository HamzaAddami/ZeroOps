import os
import asyncio
import logging
import traceback
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from app.model.pipeline import Pipeline, PipelineStage, PipelineStatus, StageType, StageStatus
from app.model.deployment import Deployment, DeploymentStatus
from app.model.project import Project
from app.core.db import Session as SessionLocal

logger = logging.getLogger(__name__)

KUBECONFIG_PATH = os.getenv("KUBECONFIG_PATH", "/app/kubeconfig.yaml")
K8S_NS_PREFIX = os.getenv("K8S_NAMESPACE_PREFIX", "idp")



def _run_cmd(cmd: list[str], input_data: str = None) -> tuple[str, str, int]:
    import subprocess
    merged_env = os.environ.copy()
    if KUBECONFIG_PATH and os.path.exists(KUBECONFIG_PATH):
        merged_env["KUBECONFIG"] = KUBECONFIG_PATH

    result = subprocess.run(
        cmd, env=merged_env, input=input_data,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout, result.stderr, result.returncode


async def _run_cmd_async(cmd: list[str], input_data: str = None) -> tuple[str, str, int]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: _run_cmd(cmd, input_data)
    )


async def _stage_deploy(project_name: str, image_tag: str, pipeline_id: str, commit_sha: str) -> tuple[bool, str, str]:
    namespace = f"{K8S_NS_PREFIX}-{project_name}".lower().replace("_", "-")

    ns_manifest = f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}"
    await _run_cmd_async(["kubectl", "apply", "-f", "-"], input_data=ns_manifest)

    manifest = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {project_name}
  namespace: {namespace}
  labels:
    app: {project_name}
    pipeline-id: "{pipeline_id}"
    commit: "{commit_sha[:8]}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {project_name}
  template:
    metadata:
      labels:
        app: {project_name}
    spec:
      containers:
      - name: {project_name}
        image: {image_tag}
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: {project_name}-svc
  namespace: {namespace}
spec:
  selector:
    app: {project_name}
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
"""
    stdout, stderr, code = await _run_cmd_async(
        ["kubectl", "apply", "-f", "-", "--namespace", namespace], input_data=manifest
    )
    if code != 0:
        return False, f"kubectl apply failed:\n{stderr[:1000]}", namespace

    stdout_roll, stderr_roll, code_roll = await _run_cmd_async(
        ["kubectl", "rollout", "status", f"deployment/{project_name}", f"--namespace={namespace}", "--timeout=120s"]
    )
    if code_roll != 0:
        return False, f"Rollout validation failed:\n{stderr_roll[:1000]}", namespace

    return True, f"Successfully deployed to cluster namespace '{namespace}' and verified rollout status.", namespace




class PipelineRunner:

    @staticmethod
    async def run(pipeline_id: str) -> None:
        db = SessionLocal()
        try:
            pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
            if not pipeline:
                return

            project = db.query(Project).filter(Project.id == pipeline.project_id).first()
            if not project:
                return

            if hasattr(pipeline, 'start'):
                pipeline.start()
            else:
                pipeline.status = PipelineStatus.running
                pipeline.started_at = datetime.utcnow()
            db.commit()

            gh_user = os.getenv("GHCR_USERNAME", "zeroops-apps").lower()
            gh_registry = os.getenv("GHCR_REGISTRY", "ghcr.io").lower()
            computed_image_tag = f"{gh_registry}/{gh_user}/{project.name}:sha-{pipeline.commit_sha[:8]}".lower()

            for stage in sorted(pipeline.stages, key=lambda s: s.order):

                if stage.status == StageStatus.success:
                    logger.info(
                        f"Stage {stage.type} completed via GitHub Actions integration. Skipping local build process.")
                    continue

                if stage.type == StageType.deploy:
                    stage.start()
                    db.commit()

                    try:
                        success, logs, deployed_ns = await _stage_deploy(
                            project.name, computed_image_tag, str(pipeline.id), pipeline.commit_sha
                        )

                        if success:
                            deployment = Deployment(
                                project_id=pipeline.project_id, pipeline_id=pipeline.id,
                                image_tag=computed_image_tag, commit_sha=pipeline.commit_sha,
                                namespace=deployed_ns, status=DeploymentStatus.running,
                                replicas_desired=1, replicas_ready=1, deployed_at=datetime.utcnow()
                            )
                            db.add(deployment)
                            project.status = "deployed"
                            stage.succeed(logs)
                        else:
                            stage.fail(logs[:500], logs)
                            project.status = "failed"

                    except Exception as stage_err:
                        db.rollback()
                        stage.fail(f"Deployment crash: {type(stage_err).__name__}", traceback.format_exc()[:1500])
                        project.status = "failed"

                    db.commit()

                if stage.status == StageStatus.failed:
                    for remaining in pipeline.stages:
                        if remaining.status == StageStatus.pending:
                            if hasattr(remaining, 'skip'):
                                remaining.skip(True)
                            else:
                                remaining.status = "skipped"

                    if hasattr(pipeline, 'finish'):
                        pipeline.finish(success=False)
                    else:
                        pipeline.status = PipelineStatus.failed
                        pipeline.finished_at = datetime.utcnow()
                    db.commit()
                    return

            if hasattr(pipeline, 'finish'):
                pipeline.finish(success=True)
            else:
                pipeline.status = PipelineStatus.success
                pipeline.finished_at = datetime.utcnow()
            db.commit()

        except Exception as e:
            logger.error(f"[PIPELINE FATAL ERROR]\n{traceback.format_exc()}")
            db.rollback()
            fallback_db = SessionLocal()
            try:
                p = fallback_db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
                if p:
                    p.status = PipelineStatus.failed
                    p.finished_at = datetime.utcnow()
                    fallback_db.commit()
            finally:
                fallback_db.close()
        finally:
            db.close()