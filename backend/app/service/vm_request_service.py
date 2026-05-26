import asyncio

from sqlalchemy.orm import Session
from fastapi import HTTPException, status, BackgroundTasks
from uuid import UUID
from datetime import datetime, timedelta
import traceback
import logging
from app.model.vm_request import VMRequest, VMRequestStatus
from app.model.user import User
from app.dto.vm_dto import VMRequestCreate, VMRequestReject
from app.service.terraform_service import TerraformService

from app.core.db import Session as SessionLocal

logger = logging.getLogger(__name__)


class VMRequestService:

    @staticmethod
    def get_all(db: Session, user: User) -> list:
        if user.role.value in ("admin", "manager"):
            return db.query(VMRequest).order_by(VMRequest.created_at.desc()).all()
        return (
            db.query(VMRequest)
            .filter(VMRequest.requester_id == user.id)
            .order_by(VMRequest.created_at.desc())
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, request_id: UUID, user: User) -> VMRequest:
        vm = db.query(VMRequest).filter(request_id == VMRequest.id).first()
        if not vm:
            raise HTTPException(404, "VM not found")
        return vm

    @staticmethod
    def create(db: Session, data: VMRequestCreate, user: User) -> VMRequest:
        active = db.query(VMRequest).filter(
            VMRequest.requester_id == user.id,
            VMRequest.status.in_([
                VMRequestStatus.pending,
                VMRequestStatus.approved,
                VMRequestStatus.ready,
                VMRequestStatus.running,
            ])
        ).first()

        if active:
            raise HTTPException(
                409,
                f"You already have active vm (status: {active.status.value})"
            )

        vm = VMRequest(
            requester_id=user.id,
            project_id=data.project_id,
            cpu_cores=data.cpu_cores,
            ram_gb=data.ram_gb,
            disk_gb=data.disk_gb,
            os=data.os,
            purpose=data.purpose,
            duration_hours=data.duration_hours,
        )
        db.add(vm)
        db.commit()
        db.refresh(vm)
        return vm

    @staticmethod
    def approve(
            db: Session,
            request_id: UUID,
            reviewer: User,
            background_tasks: BackgroundTasks
    ) -> VMRequest:
        vm = db.query(VMRequest).filter(request_id == VMRequest.id).first()
        if not vm:
            raise HTTPException(404, "VM not found")

        if vm.status != VMRequestStatus.pending:
            raise HTTPException(
                400, f"Impossible to approve — status : {vm.status.value}"
            )

        vm.approve(reviewer.id)
        db.commit()

        background_tasks.add_task(
            VMRequestService._run_provision_sync,  # wrapper sync
            str(vm.id)
        )

        db.refresh(vm)
        return vm

    @staticmethod
    def _run_provision_sync(vm_request_id: str) -> None:
        asyncio.run(VMRequestService._provision_background(vm_request_id))

    @staticmethod
    async def _provision_background(vm_request_id: str) -> None:
        db = SessionLocal()
        success = False
        error_msg = "Provisioning failed"

        try:
            vm = db.query(VMRequest).filter(VMRequest.id == vm_request_id).first()
            if not vm:
                return

            expires_at = datetime.utcnow() + timedelta(hours=vm.duration_hours)

            result = await TerraformService.provision(
                vm_request_id=str(vm.id),
                project_id=str(vm.project_id),
                cpu_cores=vm.cpu_cores,
                ram_gb=vm.ram_gb,
                disk_gb=vm.disk_gb,
                os=vm.os,
                purpose=vm.purpose,
                duration_hours=vm.duration_hours,
                expires_at=expires_at,
            )

            vm.mark_ready(
                vm_id=result["vm_id"],
                ip=result["ip_address"],
                ssh_user=result["ssh_user"],
            )
            db.commit()
            success = True
            logger.info(f"[PROVISION OK] {vm_request_id} → {result['ip_address']}")

        except Exception as e:
            logger.error(f"[PROVISION FAILED] {vm_request_id}\n{traceback.format_exc()}")
            error_msg = e.detail if hasattr(e, "detail") else str(e)
            db.rollback()
        finally:
            db.close()

        if not success:
            error_db = SessionLocal()
            try:
                vm = error_db.query(VMRequest).filter(VMRequest.id == vm_request_id).first()
                if vm:
                    vm.status = VMRequestStatus.rejected
                    vm.reject_reason = f"Provisioning failed: {error_msg}"[:255]
                    error_db.commit()
            except Exception as write_err:
                logger.error(f"[CRITICAL] Failed to write rejection: {write_err}")
            finally:
                error_db.close()

        if 'result' not in dir():
            error_db = SessionLocal()
            try:
                vm = error_db.query(VMRequest).filter(VMRequest.id == vm_request_id).first()
                if vm:
                    vm.status = VMRequestStatus.rejected
                    vm.reject_reason = "Provisioning failed — voir les logs serveur"[:255]
                    error_db.commit()
            except Exception as write_err:
                logger.error(f"[CRITICAL] Failed to write rejection: {write_err}")
            finally:
                error_db.close()

    @staticmethod
    def reject(db: Session, request_id: UUID, data: VMRequestReject, reviewer: User) -> VMRequest:
        vm = db.query(VMRequest).filter(request_id == VMRequest.id).first()
        if not vm:
            raise HTTPException(404, "VM request not found")

        if vm.status != VMRequestStatus.pending:
            raise HTTPException(400, f"Impossible to reject — status : {vm.status.value}")

        vm.reject(reviewer.id, data.reason)
        db.commit()
        db.refresh(vm)
        return vm

    @staticmethod
    async def destroy(
            db: Session,
            request_id: UUID,
            user: User,
            background_tasks: BackgroundTasks
    ) -> VMRequest:
        vm = db.query(VMRequest).filter(request_id == VMRequest.id).first()
        if not vm:
            raise HTTPException(404, "VM request not found")

        if str(vm.requester_id) != str(user.id) and user.role.value not in ("manager", "admin"):
            raise HTTPException(403, "Access denied")

        if vm.status not in (VMRequestStatus.ready, VMRequestStatus.running):
            raise HTTPException(400, f"Impossible de destruct — status : {vm.status.value}")

        background_tasks.add_task(VMRequestService._destroy_background, str(vm.id))

        vm.status = VMRequestStatus.destroyed
        db.commit()
        db.refresh(vm)
        return vm

    @staticmethod
    async def _destroy_background(vm_request_id: str) -> None:
        db = SessionLocal()
        try:
            await TerraformService.destroy(vm_request_id)
        except Exception as e:
            logger.error(f"[ERROR] Destroy failed for {vm_request_id}: {e}")
        finally:
            db.close()