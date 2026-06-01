import os
import asyncio
import subprocess
import shutil
import logging
import traceback
import json
from pathlib import Path
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
from app.model.pipeline import Pipeline, PipelineStage, PipelineStatus, StageType, StageStatus
from app.model.security_scan import SecurityScan, ScanStatus
from app.model.deployment import Deployment, DeploymentStatus
from app.model.project import Project
from app.core.db import Session as  SessionLocal

logger = logging.getLogger(__name__)

WORKSPACE_DIR = Path(os.getenv("PIPELINE_WORKSPACE_DIR", "/tmp/idp-pipelines"))
GHCR_REGISTRY = os.getenv("GHCR_REGISTRY", "ghcr.io")
GHCR_USERNAME = os.getenv("GHCR_USERNAME", "")
GHCR_TOKEN = os.getenv("GHCR_TOKEN", "")
SONAR_HOST = os.getenv("SONAR_HOST_URL", "http://localhost:9000")
SONAR_TOKEN = os.getenv("SONAR_TOKEN", "")
KUBECONFIG_PATH = os.getenv("KUBECONFIG_PATH", "/app/kubeconfig.yaml")
K8S_NS_PREFIX = os.getenv("K8S_NAMESPACE_PREFIX", "idp")


# ── Helpers ──────────────────────────────────────────────────

def _run_cmd(cmd: list[str], cwd: str = None, env: dict = None, input_data: str = None) -> tuple[str, str, int]:
    """Exécute une commande de manière synchrone et sécurisée."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if KUBECONFIG_PATH and os.path.exists(KUBECONFIG_PATH):
        merged_env["KUBECONFIG"] = KUBECONFIG_PATH

    result = subprocess.run(
        cmd, cwd=cwd, env=merged_env, input=input_data,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout, result.stderr, result.returncode


async def _run_cmd_async(cmd: list[str], cwd: str = None, env: dict = None, input_data: str = None) -> tuple[
    str, str, int]:
    """Exécute la commande dans un exécuteur pour ne pas bloquer l'Event Loop FastAPI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: _run_cmd(cmd, cwd, env, input_data)
    )


def _get_workspace(pipeline_id: str) -> Path:
    ws = WORKSPACE_DIR / pipeline_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _cleanup_workspace(pipeline_id: str):
    ws = WORKSPACE_DIR / pipeline_id
    shutil.rmtree(str(ws), ignore_errors=True)


# ── Stage Executors ───────────────────────────────────────────

async def _stage_checkout(workspace: Path, repo_url: str, commit_sha: str, branch: str) -> tuple[bool, str]:
    repo_path = workspace / "repo"
    stdout, stderr, code = await _run_cmd_async(
        ["git", "clone", "--depth", "50", "--branch", branch, repo_url, str(repo_path)]
    )
    if code != 0:
        return False, f"git clone failed:\n{stderr[:1000]}"

    stdout2, stderr2, code2 = await _run_cmd_async(
        ["git", "checkout", commit_sha], cwd=str(repo_path)
    )
    if code2 != 0:
        return False, f"git checkout failed:\n{stderr2[:500]}"

    return True, f"Checked out {commit_sha[:8]} on {branch}"


async def _stage_code_analysis(workspace: Path, project_name: str) -> tuple[bool, str]:
    if not SONAR_TOKEN:
        return True, "SonarQube not configured — skipped"

    repo_path = workspace / "repo"
    stdout, stderr, code = await _run_cmd_async(
        ["sonar-scanner",
         f"-Dsonar.projectKey={project_name}",
         f"-Dsonar.host.url={SONAR_HOST}",
         f"-Dsonar.login={SONAR_TOKEN}",
         "-Dsonar.sources=."],
        cwd=str(repo_path)
    )
    if code != 0:
        return False, f"SonarQube failed:\n{stderr[:1000]}"
    return True, stdout[:2000]


async def _stage_unit_tests(workspace: Path) -> tuple[bool, str]:
    repo_path = workspace / "repo"
    if not (repo_path / "pytest.ini").exists() and not (repo_path / "pyproject.toml").exists() and not (
            repo_path / "requirements.txt").exists():
        return True, "No test configuration or requirements found — skipped"

    stdout, stderr, code = await _run_cmd_async(
        ["python", "-m", "pytest", "--tb=short", "-q"], cwd=str(repo_path)
    )
    logs = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    if code != 0:
        return False, f"Tests failed:\n{logs[:2000]}"
    return True, logs[:2000]


async def _stage_docker_build(workspace: Path, project_name: str, commit_sha: str) -> tuple[bool, str, str]:
    repo_path = workspace / "repo"
    image_name = f"{GHCR_REGISTRY}/{GHCR_USERNAME}/{project_name}".lower()
    image_tag = f"{image_name}:sha-{commit_sha[:8]}"

    if not (repo_path / "Dockerfile").exists():
        return False, "No Dockerfile found in repository root", ""

    stdout, stderr, code = await _run_cmd_async(
        ["docker", "build", "-t", image_tag, "."], cwd=str(repo_path)
    )
    logs = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    if code != 0:
        return False, f"docker build failed:\n{logs[:2000]}", ""
    return True, logs[:2000], image_tag


async def _stage_security_scan(image_tag: str) -> tuple[bool, str, list, int, int, int, int]:
    stdout, stderr, code = await _run_cmd_async(
        ["trivy", "image", "--format", "json", "--exit-code", "0", image_tag]
    )
    if code != 0 and not stdout:
        return True, f"Trivy scan skipped (not available):\n{stderr[:300]}", [], 0, 0, 0, 0

    vulns = []
    critical = high = medium = low = 0

    try:
        data = json.loads(stdout)
        # Trivy peut retourner une liste ou un dictionnaire selon la version
        results = data.get("Results", []) if isinstance(data, dict) else []
        for result in results:
            for v in result.get("Vulnerabilities", []):
                severity = v.get("Severity", "UNKNOWN").lower()
                vulns.append({
                    "id": v.get("VulnerabilityID"),
                    "severity": severity,
                    "package": v.get("PkgName"),
                    "version": v.get("InstalledVersion"),
                    "title": v.get("Title", ""),
                })
                if severity == "critical":
                    critical += 1
                elif severity == "high":
                    high += 1
                elif severity == "medium":
                    medium += 1
                elif severity == "low":
                    low += 1
    except Exception as e:
        logger.error(f"Error parsing Trivy output: {str(e)}")

    # Bloquant si faille CRITICAL détectée
    passed = (critical == 0)
    summary = f"CVE Summary: critical={critical} high={high} medium={medium} low={low}"
    return passed, summary, vulns, critical, high, medium, low


async def _stage_push_registry(image_tag: str) -> tuple[bool, str]:
    if not GHCR_TOKEN or not GHCR_USERNAME:
        return False, "GHCR credentials (USERNAME/TOKEN) not configured"

    # Fix: Utilisation de l'argument input_data sécurisé pour éviter le blocage stdin
    stdout, stderr, code = await _run_cmd_async(
        ["docker", "login", GHCR_REGISTRY, "-u", GHCR_USERNAME, "--password-stdin"],
        input_data=GHCR_TOKEN
    )
    if code != 0:
        return False, f"Docker login failed:\n{stderr[:500]}"

    stdout2, stderr2, code2 = await _run_cmd_async(["docker", "push", image_tag])
    if code2 != 0:
        return False, f"docker push failed:\n{stderr2[:1000]}"
    return True, f"Successfully pushed {image_tag}"


async def _stage_deploy(project_name: str, image_tag: str, pipeline_id: str, commit_sha: str) -> tuple[bool, str, str]:
    namespace = f"{K8S_NS_PREFIX}-{project_name}".lower().replace("_", "-")

    # Fix: Correction de la commande kubectl apply pour la création du namespace
    ns_manifest = f"apiVersion: v1\nkind: Namespace\metadata:\n  name: {namespace}"
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

    # Attente de la validation du déploiement (Timeout 120s)
    stdout_roll, stderr_roll, code_roll = await _run_cmd_async(
        ["kubectl", "rollout", "status", f"deployment/{project_name}", f"--namespace={namespace}", "--timeout=120s"]
    )
    if code_roll != 0:
        return False, f"Rollout validation failed:\n{stderr_roll[:1000]}", namespace

    return True, f"Deployed successfully to namespace: {namespace}", namespace


# ── Main Pipeline Runner ──────────────────────────────────────

class PipelineRunner:

    @staticmethod
    async def run(pipeline_id: str) -> None:
        db = SessionLocal()
        workspace = None
        try:
            pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
            if not pipeline:
                return

            project = db.query(Project).filter(Project.id == pipeline.project_id).first()
            if not project:
                return

            workspace = _get_workspace(pipeline_id)
            pipeline.start()
            db.commit()

            # Variables partagées tout au long du cycle de vie du runner
            context = {"image_tag": "", "namespace": ""}

            for stage in sorted(pipeline.stages, key=lambda s: s.order):
                await PipelineRunner._run_stage(db, pipeline, stage, project, workspace, context)

                if stage.status == StageStatus.failed:
                    # Skip automatique des étapes restantes
                    for remaining in pipeline.stages:
                        if remaining.status == StageStatus.pending:
                            remaining.skip(True)
                    pipeline.finish(success=False)
                    project.status = "failed"
                    db.commit()
                    return

            pipeline.finish(success=True)
            db.commit()

        except Exception as e:
            logger.error(f"[PIPELINE FATAL ERROR]\n{traceback.format_exc()}")
            db.rollback()
            # Réouverture d'une session saine pour marquer l'échec
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
            if workspace:
                _cleanup_workspace(pipeline_id)
            db.close()

    @staticmethod
    async def _run_stage(db: Session, pipeline: Pipeline, stage: PipelineStage, project: Project, workspace: Path,
                         context: dict) -> None:
        stage.start()
        db.commit()

        try:
            success, logs = False, ""

            if stage.type == StageType.source_checkout:
                if not project.repository_url:
                    stage.fail("No repository URL configured", "")
                    return
                success, logs = await _stage_checkout(workspace, project.repository_url, pipeline.commit_sha,
                                                      pipeline.branch)

            elif stage.type == StageType.code_analysis:
                success, logs = await _stage_code_analysis(workspace, project.name)

            elif stage.type == StageType.unit_tests:
                success, logs = await _stage_unit_tests(workspace)

            elif stage.type == StageType.build:
                success, logs, built_tag = await _stage_docker_build(workspace, project.name, pipeline.commit_sha)
                if success:
                    context["image_tag"] = built_tag
                    logs += f"\ncontext_image_tag: {built_tag}"

            elif stage.type == StageType.security_scan:
                if not context["image_tag"]:
                    stage.fail("No image artifact discovered from previous stages", "")
                    return
                passed, logs, vulns, crit, high, med, low = await _stage_security_scan(context["image_tag"])

                scan = SecurityScan(
                    pipeline_id=pipeline.id, image_tag=context["image_tag"],
                    status=ScanStatus.passed if passed else ScanStatus.failed,
                    critical_count=crit, high_count=high, medium_count=med, low_count=low,
                    vulnerabilities=vulns, scanned_at=datetime.utcnow(), is_blocking=True
                )
                db.add(scan)
                success = passed

            elif stage.type == StageType.push_registry:
                if not context["image_tag"]:
                    stage.fail("Aborting registry push: image_tag reference missing", "")
                    return
                success, logs = await _stage_push_registry(context["image_tag"])

            elif stage.type == StageType.deploy:
                if not context["image_tag"]:
                    stage.fail("Aborting deployment: image artifact tracking identifier missing", "")
                    return
                success, logs, deployed_ns = await _stage_deploy(project.name, context["image_tag"], str(pipeline.id),
                                                                 pipeline.commit_sha)
                context["namespace"] = deployed_ns

                if success:
                    deployment = Deployment(
                        project_id=pipeline.project_id, pipeline_id=pipeline.id,
                        image_tag=context["image_tag"], commit_sha=pipeline.commit_sha,
                        namespace=deployed_ns, status=DeploymentStatus.running,
                        replicas_desired=1, replicas_ready=1, deployed_at=datetime.utcnow()
                    )
                    db.add(deployment)
                    project.status = "deployed"

            if success:
                stage.succeed(logs)
            else:
                stage.fail(logs[:500], logs)
            db.commit()

        except Exception as e:
            db.rollback()
            stage.fail(f"{type(e).__name__}: {str(e)}", traceback.format_exc()[:2000])
            db.commit()