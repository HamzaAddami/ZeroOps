import logging
import os
import json
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from fastapi import HTTPException
from app.model.vm_request import VMOperatingSystem
from app.dto.vm_dto import OS_TO_AMI, get_instance_type

OS_TO_SSH_USER = {
    VMOperatingSystem.ubuntu_22: "ubuntu",
    VMOperatingSystem.ubuntu_24: "ubuntu",
    VMOperatingSystem.debian_12: "admin",
}

WORKSPACE_DIR  = Path(os.getenv("TERRAFORM_WORKSPACES_DIR", "C:/Users/Public/zeroOps/backend/app/terraform/workspaces"))
TEMPLATE_DIR   = Path(__file__).parent.parent / "terraform" / "templates"
KEY_PAIR_NAME  = os.getenv("AWS_KEY_PAIR_NAME", "vockey")
AWS_REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

TF_BINARY_PATH = os.getenv("TERRAFORM_BINARY", "terraform")

logger = logging.getLogger(__name__)


class TerraformService:

    @staticmethod
    def _get_workspace(vm_request_id: str) -> Path:
        workspace = WORKSPACE_DIR / str(vm_request_id)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    @staticmethod
    def _render_template(vm_request_id: str, context: dict) -> str:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=False
        )
        template = env.get_template("ec2.tf.jinja2")
        return template.render(**context)

    @staticmethod
    def _write_terraform_files(workspace: Path, tf_content: str) -> None:
        (workspace / "main.tf").write_text(tf_content, encoding="utf-8")

    @staticmethod
    async def _run_terraform(workspace: Path, *args) -> tuple[str, str, int]:
        import subprocess
        env = os.environ.copy()
        env.update({
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN", ""),
            "AWS_DEFAULT_REGION": AWS_REGION,
            "TF_INPUT": "false",
            "TF_IN_AUTOMATION": "true",
        })

        cmd = [TF_BINARY_PATH] + list(args)

        def _execute():
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workspace),
                env=env,
                text=True,
                errors="replace"
            )
            stdout, stderr = process.communicate()
            return stdout, stderr, process.returncode

        stdout, stderr, code = await asyncio.to_thread(_execute)

        logger.info(f"[TF] terraform {' '.join(args)} → code={code}")
        if stderr:
            logger.warning(f"[TF STDERR] {stderr[:1000]}")

        return stdout, stderr, code

    @staticmethod
    async def provision(
        vm_request_id: str,
        project_id: str,
        cpu_cores: int,
        ram_gb: int,
        disk_gb: int,
        os: VMOperatingSystem,
        purpose: str,
        duration_hours: int,
        expires_at: datetime,
    ) -> dict:

        workspace     = TerraformService._get_workspace(vm_request_id)
        instance_type = get_instance_type(cpu_cores, ram_gb)
        ami_id        = OS_TO_AMI.get(os.value)
        ssh_user      = OS_TO_SSH_USER.get(os, "ubuntu")

        if not ami_id:
            raise HTTPException(400, f"AMI unknown {os.value}")

        if not shutil.which(TF_BINARY_PATH):
            raise HTTPException(
                500,
                f"Terraform binary not found at: {TF_BINARY_PATH}. Check your system PATH or .env file."
            )

        context = {
            "vm_request_id": str(vm_request_id),
            "project_id":    str(project_id),
            "region":        AWS_REGION,
            "ami_id":        ami_id,
            "instance_type": instance_type,
            "disk_gb":       disk_gb,
            "key_pair_name": KEY_PAIR_NAME,
            "ssh_user":      ssh_user,
            "purpose":       purpose[:50],
            "expires_at":    expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        tf_content = TerraformService._render_template(str(vm_request_id), context)
        TerraformService._write_terraform_files(workspace, tf_content)

        # terraform init
        stdout, stderr, code = await TerraformService._run_terraform(
            workspace, "init", "-no-color"
        )
        if code != 0:
            raise HTTPException(500, f"terraform init failed: {stderr[:500].strip()}")

        #  terraform apply
        stdout, stderr, code = await TerraformService._run_terraform(
            workspace, "apply", "-auto-approve", "-no-color"
        )
        if code != 0:
            raise HTTPException(500, f"terraform apply failed: {stderr[:500].strip()}")

        #  terraform output
        stdout, stderr, code = await TerraformService._run_terraform(
            workspace, "output", "-json"
        )
        if code != 0:
            raise HTTPException(500, f"terraform output failed: {stderr[:500].strip()}")

        try:
            outputs = json.loads(stdout)
            vm_id      = outputs["instance_id"]["value"]
            ip_address = outputs["public_ip"]["value"]
            ssh_user   = outputs["ssh_user"]["value"]
        except (json.JSONDecodeError, KeyError) as e:
            raise HTTPException(500, f"Error in reading Terraform's outputs: {e}")

        return {
            "vm_id":      vm_id,
            "ip_address": ip_address,
            "ssh_user":   ssh_user,
        }

    @staticmethod
    async def destroy(vm_request_id: str) -> None:
        workspace = TerraformService._get_workspace(vm_request_id)

        if not (workspace / "main.tf").exists():
            return

        if not shutil.which(TF_BINARY_PATH):
            raise HTTPException(500, f"Terraform binary not found at: {TF_BINARY_PATH}")

        stdout, stderr, code = await TerraformService._run_terraform(
            workspace, "destroy", "-auto-approve", "-no-color"
        )

        if code != 0:
            raise HTTPException(500, f"terraform destroy failed: {stderr[:500].strip()}")

        shutil.rmtree(str(workspace), ignore_errors=True)