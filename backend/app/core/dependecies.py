from fastapi import HTTPException, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from app.core.opa import check_opa
from app.core.db import get_db, Session
from app.model.user import User
from app.core.security import decode_token
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload or payload.get('type') != 'access':
        raise HTTPException(401, "Token invalid")

    current_user_id = payload['sub']

    try:
        valid_uuid = uuid.UUID(current_user_id)
    except ValueError:
        raise HTTPException(403, "Invalid user id")

    user = db.query(User).filter(User.id == valid_uuid).first()

    if not user:
        raise HTTPException(401, "User not found")

    return user

async def authorize(
        request: Request,
        current_user: User = Depends(get_current_user)
)-> User:
    await check_opa(
        method=request.method,
        path=request.url.path,
        user_id=str(current_user.id),
        role=current_user.role.value,
        token_type='access'
    )
    return current_user
