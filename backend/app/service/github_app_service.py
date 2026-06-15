import os
import time
import logging
import httpx
import jwt
import nacl.encoding
import nacl.public

logger = logging.getLogger(__name__)

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "zeroops-app.private-key.pem")
GITHUB_APP_INSTALLATION_ID = os.getenv("GITHUB_APP_INSTALLATION_ID", "")
GITHUB_ORG = os.getenv("GITHUB_ORG", "ZeroOps-PFA")


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


async def inject_repo_secret(
        repo_owner: str,
        repo_name: str,
        secret_name: str,
        secret_value: str,
        token: str,
) -> bool:
    async with httpx.AsyncClient() as client:
        key_res = await client.get(
            f"https://api.github.com/repos/{repo_owner}/{repo_name}"
            f"/actions/secrets/public-key",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        if key_res.status_code != 200:
            logger.error(f"Failed to get public key: {key_res.text}")
            return False

        key_data = key_res.json()
        public_key = key_data["key"]
        key_id = key_data["key_id"]

        import base64
        pub_key_bytes = base64.b64decode(public_key)
        sealed_box = nacl.public.SealedBox(
            nacl.public.PublicKey(pub_key_bytes)
        )
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

        put_res = await client.put(
            f"https://api.github.com/repos/{repo_owner}/{repo_name}"
            f"/actions/secrets/{secret_name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "encrypted_value": encrypted_b64,
                "key_id": key_id,
            },
        )

        if put_res.status_code in (201, 204):
            logger.info(
                f"✅ Secret '{secret_name}' injected into "
                f"{repo_owner}/{repo_name}"
            )
            return True

        logger.error(f"Secret injection failed: {put_res.text}")
        return False


async def inject_workflow_to_repo(repo_owner: str, repo_name: str, token: str) -> bool:
    import base64
    url = (
        f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        f"/contents/.github/workflows/secops-ci.yml"
    )
    sonar_project_key = f"{repo_owner}_{repo_name}".lower().replace("-", "_")

    workflow_content = f"""name: SecOps Cloud Pipeline

on:
  push:
    branches: [ "main" ]

jobs:
  security-and-build:
    runs-on: ubuntu-latest
    env:
      FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
    
    permissions:
      contents: read
      packages: write
      id-token: write  
    
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: SonarCloud Scan
        uses: SonarSource/sonarqube-scan-action@v3
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
          SONAR_TOKEN:  ${{{{ secrets.SONAR_TOKEN }}}}
        with:
          args: >
            -Dsonar.organization={repo_owner.lower()}
            -Dsonar.projectKey={sonar_project_key}
            -Dsonar.host.url=https://sonarcloud.io

      - name: Run Trivy Security Scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          format:    'table'
          severity:  'CRITICAL,HIGH'
          exit-code: '1'

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Build and Push Docker Image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/{repo_owner.lower()}/{repo_name.lower()}:sha-${{{{ github.sha }}}}
"""

    encoded = base64.b64encode(workflow_content.encode()).decode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        check = await client.get(url, headers=headers)
        if check.status_code == 200:
            logger.info(f"Workflow already exists in {repo_name} — skipping")
            return True

        response = await client.put(url, headers=headers, json={
            "message": "chore: inject ZeroOps SecOps CI pipeline",
            "content": encoded,
            "branch": "main",
        })

        if response.status_code == 201:
            logger.info(f"Workflow injected into {repo_owner}/{repo_name}")
            return True

        logger.error(f"Injection failed: {response.status_code} — {response.text}")
        return False