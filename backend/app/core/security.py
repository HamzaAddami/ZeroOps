from jose import jwt, JWTError
from datetime import datetime, timedelta
from passlib.context import CryptContext

import os
import pyotp
import secrets


SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM')
ACCESS_EXPIRE  = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
MFA_EXPIRE = int(os.getenv("JWT_MFA_EXPIRE_MINUTES", "1440"))
APP_NAME = str(os.getenv("APP_NAME"))

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str, email: str, role: str) -> str:

    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'type': "access",
        'exp' : datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def create_mfa_pending_token(user_id: str, email: str, role: str) -> str:
    payload = {
        'sub': user_id,
        'type': "mfa_pending",
        'exp': datetime.utcnow() + timedelta(minutes=MFA_EXPIRE),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None

def generate_mfa_secret() -> str:
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str)  -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=APP_NAME)

def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)

def generate_recovery_codes(count:int = 8) -> list[str]:
    return [
        f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        for _ in range(count)
    ]

def hash_recover_codes(codes: list[str]) -> str:
    return ','.join(pwd_context.hash(code) for code in codes)

def verify_recovery_codes(palin_code: str, stored_hashes: str) -> tuple[bool, str]:
    for hashed in stored_hashes.split(","):
        if pwd_context.verify(hashed, palin_code):
            return True, hashed
    return False, ""
