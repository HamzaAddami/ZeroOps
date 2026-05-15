from ..core.db import Session
from ..core.credentials import generate_initial_credentials
from app.model.user import User, UserRole
from fastapi import HTTPException
from ..core.security import hash_password


class UserService:

    @staticmethod
    def _check_email_exists(db: Session, email: str) -> bool:
        return db.query(User).filter(User.email == email).first() is not None

    @staticmethod
    def login_user(db: Session, username: str, password: str) -> User:
        pass

    @staticmethod
    def find_user_by_id(db: Session, user_id: int) -> User:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    async def create_user_by_admin(db: Session, full_name: str, email:str, role: UserRole) -> dict:
        if UserService._check_email_exists(db, email):
            raise HTTPException(status_code=409, detail="User already exists")

        existing_usernames = [u[0] for u in db.query(User.username).all()]
        credentials = generate_initial_credentials(full_name, existing_usernames)
        temp_password = credentials.get('password')
        user = User(
            full_name=full_name,
            username=credentials.get('username'),
            email=email,
            role=role,
            hashed_password=hash_password(temp_password),
            must_change_password=credentials.get('must_change_password'),
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        return {"user": user, "temp_password": temp_password}

    @staticmethod
    async def get_user_by_id(db: Session, user_id: int) -> User:
        existing = db.query(User).filter(User.id == user_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        return existing

    @staticmethod
    async def delete_user_by_admin(db: Session, user_id: int) -> None:
        pass


        
