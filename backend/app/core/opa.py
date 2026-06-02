import httpx
import os
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

OPA_URL = os.getenv("OPA_URL")

async def check_opa(
    method: str,
    path: str,
    user_id: str,
    role: str,
    token_type: str = "access",
    resource_owner_id: str = None,
    project_members: list = None,
    project_manager_id: str = None,
) -> None:
    opa_input = {
        "input": {
            "method": method,
            "path": path,
            "user_id": user_id,
            "role": role,
            "token_type": token_type,
            "resource_owner_id": resource_owner_id,
            "project_members": project_members or [],
            "project_manager_id": project_manager_id,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{OPA_URL}/v1/data/authz/allow",
                json=opa_input
            )
            resp.raise_for_status()
            result = resp.json()

    except httpx.TimeoutException:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authorization service unavailable"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"OPA error: {e.response.status_code}"
        )
    except httpx.RequestError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cannot reach authorization service"
        )

    if not result.get("result", False):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Access denied"
        )