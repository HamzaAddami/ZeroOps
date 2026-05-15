import httpx
import os
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

OPA_URL = os.getenv("OPA_URL")

async def check_opa(
    method: str,
    path: str,
    user_id: str,
    role: str,
    token_type: str = "access",
    resource_owner_id: str = None
) -> None:
    opa_input = {
        "input": {
            "method":            method,
            "path":              path,
            "user_id":           user_id,
            "role":              role,
            "token_type":        token_type,
            "resource_owner_id": resource_owner_id,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{OPA_URL}/v1/data/authz/allow",
                json=opa_input
            )
            result = resp.json()

    except httpx.TimeoutException:
        raise HTTPException(503, "OPA service unavailable")

    if not result.get("result", False):
        raise HTTPException(401, "Access denied")

