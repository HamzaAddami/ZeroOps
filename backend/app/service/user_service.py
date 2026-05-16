from datetime import datetime, timezone
from ..core.db import Session
from ..core.credentials import generate_initial_credentials, generate_temp_password
from app.model.user import User, UserRole, MAX_FAILED_ATTEMPTS, LOCKOUT_DURATION_MINUTES, TokenBlacklist
from fastapi import HTTPException
from ..core.security import *
from uuid import UUID

class UserService:

    @staticmethod
    def _check_email_exists(db: Session, email: str) -> bool:
        return db.query(User).filter(User.email == email).first() is not None

    # Auth

    @staticmethod
    def login_user(db: Session, username: str, password: str) -> dict:
        user = db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user and user.is_locked():
            remaining = user.get_lockout_remaining()
            raise HTTPException(423, f"Account is locked retry in {remaining} seconds")

        if not user or not verify_password(password, user.hashed_password):
            if user:
                user.record_failed_login()
                db.commit()
                remaining = MAX_FAILED_ATTEMPTS - user.failed_login_attempts
                if remaining > 0:
                    message = f"Wrong password . {remaining} attempts remaining"
                else:
                    message = f"Account locked for {LOCKOUT_DURATION_MINUTES} minutes"
            else:
                message = "Invalid username or password"
            raise HTTPException(401, message)

        if not user.is_active:
            raise HTTPException(401, "Account is disabled. Contact system administrator.")

        user.reset_failed_login()
        db.commit()

        if user.must_change_password:
            return {
                "must_change_password": True,
                "change_token": create_mfa_pending_token(str(user.id)),
                "message": "Changed your password for continue."
            }
        if user.mfa_enabled:
            return {
                "mfa_required": True,
                "mfa_token": create_mfa_pending_token(str(user.id)),
            }

        return {
            "access_token": create_token(
                str(user.id), user.email, user.role.value
            ),
            "token_type": "bearer",
        }

    @staticmethod
    def logout_user(db: Session, token: str) -> dict:
        existing_token = db.query(TokenBlacklist).filter(TokenBlacklist.token == token).first()
        if existing_token:
            raise HTTPException(400, "Already logged out")
        payload = decode_token(token)
        exp_timestamp = payload.get("exp")
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        blacklisted = TokenBlacklist(token=token, expired_at=exp_datetime)
        db.add(blacklisted)
        db.commit()

        return {"message": "Logged out successfully"}

    @staticmethod
    def change_password(
            db: Session,
            user: User,
            old_password: str,
            new_password: str,
            confirm_password: str
    ) -> dict:
        if new_password != confirm_password:
            raise HTTPException(400, "Password mismatch")

        if len(new_password) < 8:
            raise HTTPException(400, "At least 8 characters required")

        if not user.must_change_password:
            if not verify_password(old_password, user.hashed_password):
                raise HTTPException(401, "Current password is incorrect")

        if verify_password(new_password, user.hashed_password):
            raise HTTPException(400, "New password should be different")

        user.complete_password_change(hash_password(new_password))
        db.commit()

        if user.mfa_enabled:
            return {
                "mfa_required": True,
                "mfa_token": create_mfa_pending_token(str(user.id)),
                "message": "Password changed successfully. Verify your MFA",
            }

        return {
            "access_token": create_token(
                str(user.id), user.email, user.role.value
            ),
            "token_type": "bearer",
            "message": "Password changed successfully.",
        }

    # MFA

    @staticmethod
    def setup_mfa(db: Session, user: User) -> dict:
        if user.mfa_enabled:
            raise HTTPException(400, "MFA already active")

        secret = generate_mfa_secret()
        user.mfa_secret = secret
        db.commit()

        return {
            "secret": secret,
            "qr_uri": get_totp_uri(secret, user.email),
            "message": "Scan the QR code and  POST /auth/mfa/confirm",
        }

    @staticmethod
    def confirm_mfa(db: Session, user: User, code: str) -> dict:
        if not user.mfa_secret:
            raise HTTPException(400, "Send first POST /auth/mfa/setup")

        if not verify_totp(user.mfa_secret, code):
            raise HTTPException(401, "Invalid code. verify your authenticator")

        recovery_codes = generate_recovery_codes(8)
        user.mfa_recovery_codes = hash_recover_codes(recovery_codes)
        user.mfa_enabled = True
        db.commit()

        return {
            "message": "MFA activated successfully.",
            "recovery_codes": recovery_codes,  # show one time
        }

    @staticmethod
    def verify_mfa(db: Session, user: User, code: str) -> dict:
        if not user.mfa_secret:
            raise HTTPException(400, "MFA not configured")

        if verify_totp(user.mfa_secret, code):
            return {
                "access_token": create_token(
                    str(user.id), user.email, user.role.value
                ),
                "token_type": "bearer",
            }

        if user.mfa_recovery_codes:
            valid, used_hash = verify_recovery_codes(code, user.mfa_recovery_codes)
            if valid:
                remaining = ",".join(
                    h for h in user.mfa_recovery_codes.split(",")
                    if h != used_hash
                )
                user.mfa_recovery_codes = remaining or None
                db.commit()

                return {
                    "access_token": create_token(
                        str(user.id), user.email, user.role.value
                    ),
                    "token_type": "bearer",
                    "recovery_used": True,
                }

        raise HTTPException(401, "MFA code invalid")

    @staticmethod
    def disable_mfa(db: Session, user: User, code: str) -> dict:
        if not user.mfa_enabled:
            raise HTTPException(400, "MFA not active")
        if not verify_totp(user.mfa_secret, code):
            raise HTTPException(401, "Invalid code")

        user.mfa_secret = None
        user.mfa_enabled = False
        user.mfa_recovery_codes = None
        db.commit()

        return {"message": "MFA deactivated"}

    @staticmethod
    def find_user_by_id(db: Session, user_id: int) -> User:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    async def create_user_by_admin(db: Session, full_name: str, email:str, role: UserRole, created_by: User) -> dict:
        if UserService._check_email_exists(db, email):
            raise HTTPException(status_code=409, detail="User already exists")

        existing_usernames = [u[0] for u in db.query(User.username).all()]
        credentials = generate_initial_credentials(full_name, existing_usernames)
        temp_password = credentials.get('password')
        user = User(
            full_name=full_name,
            username=credentials['username'],
            email=email,
            role=role,
            hashed_password=hash_password(temp_password),
            must_change_password=credentials.get('must_change_password'),
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        return {"user": user, "temp_password": temp_password}

    # Admin management

    @staticmethod
    async def get_user_by_id(db: Session, user_id: UUID) -> User:
        existing = db.query(User).filter(User.id == user_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        return existing

    @staticmethod
    def get_all_users(db: Session) -> list[User]:
        return db.query(User).order_by(User.created_at.desc()).all()

    @staticmethod
    async def delete_user_by_admin(db: Session, user_id: int) -> None:
        pass

    @staticmethod
    def reset_password(db: Session, user_id: UUID, admin: User) -> dict:
        user = db.query(User).filter(User.id == user_id).first()

        if user and user.id != admin.id:
            raise HTTPException(403, "Impossible to reset password for admins")

        new_temp = generate_temp_password()
        user.hashed_password = hash_password(new_temp)
        user.force_password_change()

        user.mfa_secret = None
        user.mfa_enabled = False
        user.mfa_recovery_codes = None

        db.commit()

        return {
            "username": user.username,
            "temp_password": new_temp,
            "message": "MFA successfully reset. User should reconfigure MFA.",
        }

    @staticmethod
    def update_role(
            db: Session,
            user_id: UUID,
            new_role: UserRole,
            admin: User
    ) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user.id == admin.id:
            raise HTTPException(400, "Impossible to modify role")
        user.role = new_role
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def activate_user(db: Session, user_id: UUID) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        user.active()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def ban_user(db: Session, user_id: UUID, reason: str, admin: User) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user.id == admin.id:
            raise HTTPException(400, "Impossible to ban yourself")
        user.ban(reason)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def delete_user(db: Session, user_id: UUID, admin: User) -> dict:
        user = db.query(User).filter(User.id == user_id).first()
        if user.id == admin.id:
            raise HTTPException(400, "Impossible to delete yourself")
        db.delete(user)
        db.commit()
        return {"message": f"User '{user.username}' deleted successfully."}

    @staticmethod
    def unlock_user(db: Session, user_id: UUID) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        user.reset_failed_login()
        db.commit()
        db.refresh(user)
        return user



        
