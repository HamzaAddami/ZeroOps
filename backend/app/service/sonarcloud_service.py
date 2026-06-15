import os
import logging
import httpx

logger = logging.getLogger(__name__)

SONARCLOUD_TOKEN  = os.getenv("SONARCLOUD_TOKEN", "")
SONARCLOUD_ORG    = os.getenv("SONARCLOUD_ORG", "")
SONARCLOUD_URL    = "https://sonarcloud.io/api"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {SONARCLOUD_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


async def create_sonar_project(repo_name: str) -> bool:

    project_key = f"{SONARCLOUD_ORG}_{repo_name}".lower().replace("-", "_")

    async with httpx.AsyncClient() as client:
        check = await client.get(
            f"{SONARCLOUD_URL}/projects/search",
            headers=_headers(),
            params={"organization": SONARCLOUD_ORG, "projects": project_key},
        )
        if check.status_code == 200:
            components = check.json().get("components", [])
            if components:
                logger.info(f"SonarCloud project '{project_key}' already exists")
                return True

        response = await client.post(
            f"{SONARCLOUD_URL}/projects/create",
            headers=_headers(),
            data={
                "name":         repo_name,
                "project":      project_key,
                "organization": SONARCLOUD_ORG,
                "visibility":   "private",
            },
        )

        if response.status_code == 200:
            logger.info(f"SonarCloud project created: {project_key}")
            return True

        logger.error(f"SonarCloud project creation failed: {response.text}")
        return False


async def generate_sonar_project_token(repo_name: str) -> str | None:

    project_key = f"{SONARCLOUD_ORG}_{repo_name}".lower().replace("-", "_")
    token_name  = f"zeroops-{repo_name}-ci"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SONARCLOUD_URL}/user_tokens/generate",
            headers=_headers(),
            data={
                "name":       token_name,
                "type":       "standard",
                "projectKey": project_key,
            },
        )

        if response.status_code == 200:
            token = response.json().get("token")
            logger.info(f"SonarCloud token generated for {repo_name}")
            return token

        logger.error(f"Token generation failed: {response.text}")
        return None


async def get_project_status(repo_name: str) -> dict | None:

    project_key = f"{SONARCLOUD_ORG}_{repo_name}".lower().replace("-", "_")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SONARCLOUD_URL}/qualitygates/project_status",
            headers=_headers(),
            params={"projectKey": project_key},
        )

        if response.status_code == 200:
            return response.json().get("projectStatus")

        logger.error(f"Quality gate status fetch failed: {response.text}")
        return None