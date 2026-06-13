import os
import time
import logging
import httpx
import jwt

logger = logging.getLogger(__name__)

GITHUB_APP_ID               = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH     = os.getenv("GITHUB_PRIVATE_KEY_PATH", "zeroops-app.private-key.pem")
GITHUB_APP_INSTALLATION_ID  = os.getenv("GITHUB_APP_INSTALLATION_ID", "")
GITHUB_ORG                  = os.getenv("GITHUB_ORG", "ZeroOps-PFA")


def _generate_jwt() -> str:
    with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()
    return jwt.encode(
        {
            "iat": int(time.time()) - 60,
            "exp": int(time.time()) + (10 * 60),
            "iss": GITHUB_APP_ID,
        },
        private_key,
        algorithm="RS256",
    )


async def get_installation_token() -> str:
    jwt_token = _generate_jwt()
    url = f"https://api.github.com/app/installations/{GITHUB_APP_INSTALLATION_ID}/access_tokens"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        response.raise_for_status()
        return response.json()["token"]


async def add_repo_to_app_installation(repo_id: int) -> bool:
    try:
        jwt_token = _generate_jwt()
        url = (
            f"https://api.github.com/orgs/{GITHUB_ORG}"
            f"/installations/{GITHUB_APP_INSTALLATION_ID}"
            f"/repositories/{repo_id}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })

            if response.status_code == 204:
                logger.info(f"Repo {repo_id} added to org installation ({GITHUB_ORG})")
                return True

            if response.status_code == 422:
                logger.info(f"Repo {repo_id} already in installation — skipping")
                return True

            logger.error(
                f"Failed to add repo {repo_id} to installation: "
                f"{response.status_code} — {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"add_repo_to_app_installation error: {e}")
        return False


async def get_repo_id(repo_owner: str, repo_name: str) -> int | None:
    try:
        token = await get_installation_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_owner}/{repo_name}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.status_code == 200:
                return response.json()["id"]

            logger.error(
                f"Repo not found: {repo_owner}/{repo_name} "
                f"({response.status_code})"
            )
            return None

    except Exception as e:
        logger.error(f"get_repo_id error: {e}")
        return None


async def list_org_installation_repos() -> list[dict]:
    try:
        token = await get_installation_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/installation/repositories",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()
            return [
                {"id": r["id"], "name": r["name"], "full_name": r["full_name"]}
                for r in data.get("repositories", [])
            ]

    except Exception as e:
        logger.error(f"list_org_installation_repos error: {e}")
        return []