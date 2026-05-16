import uuid
from typing import Type
from fastapi import HTTPException, Request, Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.opa import check_opa
from app.core.db import get_db
from app.model.user import User, TokenBlacklist, UserRole
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# Auth

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Type[User]:
    blacklisted = db.query(TokenBlacklist).filter(
        token == TokenBlacklist.token
    ).first()
    if blacklisted:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token has been revoked"
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token"
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "MFA authentication required"
        )

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid token payload"
        )

    user = db.query(User).filter(user_uuid == User.id).first()

    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Account {user.status.value}"
        )

    return user


def get_mfa_pending_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Type[User]:

    payload = decode_token(token)

    if not payload or payload.get("type") != "mfa_pending":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Valid MFA token required"
        )

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid token payload"
        )

    user = db.query(User).filter(user_uuid == User.id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not found"
        )

    return user



async def authorize(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> User:

    await check_opa(
        method=request.method,
        path=request.url.path,
        user_id=str(current_user.id),
        role=current_user.role.value,
        token_type="access"
    )
    return current_user


def authorize_project(project_id_param: str = "project_id"):
    """
    Usage dans une route :
        current_user: User = Depends(authorize_project("project_id"))
    """
    async def _inner(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        from app.model.project import Project

        project_id = request.path_params.get(project_id_param)

        project_members    = []
        project_manager_id = None
        resource_owner_id  = None

        if project_id:
            try:
                project_uuid = uuid.UUID(str(project_id))
            except ValueError:
                raise HTTPException(400, "Invalid project ID")

            project = db.query(Project).filter(
                project_uuid == Project.id
            ).first()

            if not project:
                raise HTTPException(404, "Project not found")

            project_members = [str(m.id) for m in project.members]

            manager = next(
                (m for m in project.members if m.role.value == "manager"),
                None
            )
            project_manager_id = str(manager.id) if manager else None

        await check_opa(
            method=request.method,
            path=request.url.path,
            user_id=str(current_user.id),
            role=current_user.role.value,
            token_type="access",
            project_members=project_members,
            project_manager_id=project_manager_id,
            resource_owner_id=resource_owner_id,
        )

        return current_user

    return _inner


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.role == UserRole.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admin access required"
        )
    return current_user