import os
import asyncio
import logging
import traceback
from datetime import datetime
from sqlalchemy.orm import Session

from app.model.pipeline import Pipeline, PipelineStage, PipelineStatus, StageType, StageStatus
from app.model.deployment import Deployment, DeploymentStatus
from app.model.project import Project, ProjectStatus
from app.core.db import Session as SessionLocal
from app.service.github_app_service import GITHUB_ORG

logger = logging.getLogger(__name__)

KUBECONFIG_PATH = os.getenv("KUBECONFIG_PATH", "/etc/rancher/k3s/k3s.yaml")
K8S_NS_PREFIX   = os.getenv("K8S_NAMESPACE_PREFIX", "idp")
ARGOCD_SERVER   = os.getenv("ARGOCD_SERVER", "https://argocd.local")
ARGOCD_TOKEN    = os.getenv("ARGOCD_TOKEN", "")
GHCR_USERNAME   = os.getenv("GHCR_USERNAME", "zeroops-apps").lower()
GITHUB_ORG      = os.getenv("GITHUB_ORG")
GHCR_REGISTRY   = os.getenv("GHCR_REGISTRY", "ghcr.io").lower()


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


async def _run_cmd_async(cmd, input_data=None):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _run_cmd(cmd, input_data))


async def _ensure_namespace(namespace: str) -> None:
    manifest = f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}"
    await _run_cmd_async(["kubectl", "apply", "-f", "-"], input_data=manifest)


async def _apply_argocd_application(
    project_name: str,
    image_tag: str,
    namespace: str,
    pipeline_id: str,
) -> tuple[bool, str]:

    app_name = f"{project_name}-app".lower().replace("_", "-")

    app_manifest = f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}
  namespace: argocd
  labels:
    zeroops-pipeline: "{pipeline_id[:8]}"
spec:
  project: default
  source:
    repoURL: https://github.com/{os.getenv('GITHUB_ORG', 'ZeroOps-PFA')}/{project_name}
    targetRevision: HEAD
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: {namespace}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/template/spec/containers/0/image
"""

    stdout, stderr, code = await _run_cmd_async(
        ["kubectl", "apply", "-f", "-"], input_data=app_manifest
    )
    if code != 0:
        return False, f"ArgoCD Application apply failed:\n{stderr[:1000]}"

    patch = (
        f'{{"spec":{{"template":{{"spec":{{"containers":'
        f'[{{"name":"{project_name}","image":"{image_tag}"}}]}}}}}}}}'
    )
    stdout2, stderr2, code2 = await _run_cmd_async([
        "kubectl", "patch", "deployment", project_name,
        "-n", namespace,
        "--type=merge",
        f"--patch={patch}"
    ])

    stdout3, stderr3, code3 = await _run_cmd_async([
        "kubectl", "rollout", "status",
        f"deployment/{project_name}",
        f"--namespace={namespace}",
        "--timeout=120s"
    ])
    if code3 != 0:
        return False, f"Rollout timeout:\n{stderr3[:800]}"

    return True, f"ArgoCD Application '{app_name}' synced. Image: {image_tag}. Namespace: {namespace}"


async def _stage_deploy(
    project_name: str,
    image_tag: str,
    pipeline_id: str,
    commit_sha: str,
) -> tuple[bool, str, str]:
    namespace = f"{K8S_NS_PREFIX}-{project_name}".lower().replace("_", "-")
    await _ensure_namespace(namespace)

    if not ARGOCD_TOKEN:
        logger.warning("ARGOCD_TOKEN not set — falling back to direct kubectl deploy")
        return await _stage_deploy_kubectl(project_name, image_tag, pipeline_id, commit_sha, namespace)

    success, logs = await _apply_argocd_application(project_name, image_tag, namespace, pipeline_id)
    return success, logs, namespace


async def _stage_deploy_kubectl(
    project_name: str,
    image_tag: str,
    pipeline_id: str,
    commit_sha: str,
    namespace: str,
) -> tuple[bool, str, str]:
    manifest = f"""apiVersion: apps/v1
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
        ["kubectl", "apply", "-f", "-", "--namespace", namespace],
        input_data=manifest
    )
    if code != 0:
        return False, f"kubectl apply failed:\n{stderr[:1000]}", namespace

    stdout2, stderr2, code2 = await _run_cmd_async([
        "kubectl", "rollout", "status",
        f"deployment/{project_name}",
        f"--namespace={namespace}",
        "--timeout=120s"
    ])
    if code2 != 0:
        return False, f"Rollout failed:\n{stderr2[:800]}", namespace

    return True, f"Deployed to '{namespace}' via kubectl. Rollout verified.", namespace


class PipelineRunner:

    @staticmethod
    async def run(pipeline_id: str) -> None:
        db: Session = SessionLocal()
        try:
            pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
            if not pipeline:
                return

            project = db.query(Project).filter(Project.id == pipeline.project_id).first()
            if not project:
                return

            pipeline.start()
            db.commit()

            image_tag = (
                f"{GHCR_REGISTRY}/{GITHUB_ORG}/{project.name}"
                f":sha-{pipeline.commit_sha}"
            ).lower()

            for stage in sorted(pipeline.stages, key=lambda s: s.order):

                if stage.status == StageStatus.success:
                    logger.info(f"Stage {stage.type} already success — skipping")
                    continue

                if stage.type == StageType.deploy:
                    stage.start()
                    db.commit()

                    try:
                        success, logs, deployed_ns = await _stage_deploy(
                            project.name, image_tag,
                            str(pipeline.id), pipeline.commit_sha
                        )

                        if success:
                            deployment = Deployment(
                                project_id=pipeline.project_id,
                                pipeline_id=pipeline.id,
                                image_tag=image_tag,
                                commit_sha=pipeline.commit_sha,
                                namespace=deployed_ns,
                                status=DeploymentStatus.running,
                                replicas_desired=1,
                                replicas_ready=1,
                                deployed_at=datetime.utcnow(),
                            )
                            db.add(deployment)
                            project.status = ProjectStatus.deployed
                            stage.succeed(logs)
                        else:
                            stage.fail(logs[:500], logs)
                            project.status = ProjectStatus.failed

                    except Exception as e:
                        db.rollback()
                        tb = traceback.format_exc()[:1500]
                        stage.fail(f"Deploy crash: {type(e).__name__}", tb)
                        project.status = ProjectStatus.failed

                    db.commit()

                if stage.status == StageStatus.failed:
                    for remaining in pipeline.stages:
                        if remaining.status == StageStatus.pending:
                            remaining.skip(True)
                    pipeline.finish(success=False)
                    db.commit()
                    return

            pipeline.finish(success=True)
            db.commit()

        except Exception:
            logger.error(f"[PIPELINE FATAL]\n{traceback.format_exc()}")
            db.rollback()
            fallback = SessionLocal()
            try:
                p = fallback.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
                if p:
                    p.status = PipelineStatus.failed
                    p.finished_at = datetime.utcnow()
                    fallback.commit()
            finally:
                fallback.close()
        finally:
            db.close()