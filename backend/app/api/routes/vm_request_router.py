from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.core.db import get_db
from app.core.dependecies import authorize, authorize_project, require_admin
from app.model.user import User
from app.dto.vm_dto import (
    VMRequestCreate,
    VMRequestReject,
    VMRequestResponse,
)
from app.service.vm_request_service import VMRequestService

vm_router = APIRouter(prefix="/vm-requests", tags=["VM Requests"])


@vm_router.get("/", response_model=List[VMRequestResponse])
async def list_vm_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return VMRequestService.get_all(db, current_user)


@vm_router.post("/", response_model=VMRequestResponse, status_code=201)
async def create_vm_request(
    data: VMRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize_project("project_id"))
):

    return VMRequestService.create(db, data, current_user)


@vm_router.get("/{request_id}", response_model=VMRequestResponse)
async def get_vm_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return VMRequestService.get_by_id(db, request_id, current_user)


@vm_router.post("/{request_id}/approve", response_model=VMRequestResponse)
async def approve_vm_request(
    request_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return await VMRequestService.approve(
        db, request_id, current_user, background_tasks
    )


@vm_router.post("/{request_id}/reject", response_model=VMRequestResponse)
async def reject_vm_request(
    request_id: UUID,
    data: VMRequestReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return VMRequestService.reject(db, request_id, data, current_user)


@vm_router.post("/{request_id}/destroy", response_model=VMRequestResponse)
async def destroy_vm(
    request_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(authorize)
):
    return await VMRequestService.destroy(
        db, request_id, current_user, background_tasks
    )