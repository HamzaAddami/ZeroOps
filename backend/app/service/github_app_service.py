import os
import time
import logging
import httpx
import jwt

logger = logging.getLogger(__name__)

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "zeroops-app.private-key.pem")
GITHUB_APP_INSTALLATION_ID = os.getenv("GITHUB_APP_INSTALLATION_ID", "")


def _generate_jwt() -> str:
    with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()
    payload = {
        "iat": int(time.time()) - 60,
        "exp": int(time.time()) + (10 * 60),
        "iss": GITHUB_APP_ID
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token() -> str:
    jwt_token = _generate_jwt()
    url = f"https://api.github.com/app/installations/{GITHUB_APP_INSTALLATION_ID}/access_tokens"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json"
        })
        response.raise_for_status()
        return response.json()["token"]


async def add_repo_to_app_installation(repo_id: int) -> bool:
    """
    Ajoute un repo à l'installation existante de la GitHub App
    PUT /user/installations/{installation_id}/repositories/{repository_id}
    """
    try:
        token = await get_installation_token()
        url = f"https://api.github.com/app/installations/{GITHUB_APP_INSTALLATION_ID}/repositories/{repo_id}"

        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            })

            if response.status_code == 204:
                logger.info(f"✅ Repo {repo_id} added to installation GitHub App ")
                return True
            else:
                logger.error(f"ERROR in adding Repo : {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f" ERROR add_repo_to_app_installation: {e}")
        return False


async def get_repo_id(repo_owner: str, repo_name: str) -> int | None:
    "Get numeric ID of repos"
    try:
        token = await get_installation_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_owner}/{repo_name}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json"
                }
            )
            if response.status_code == 200:
                return response.json()["id"]
            logger.error(f"Repo not found : {repo_owner}/{repo_name}")
            return None
    except Exception as e:
        logger.error(f"ERROR get_repo_id: {e}")
        return None