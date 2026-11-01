"""GAGOS's own GitHub identity: a GitHub App, so its work is opened as its own.

Operator, 2026-10-30: "GAGOS only make its own PR for its own work". Until
this App exists GAGOS's PRs open with the operator's ``gh`` login and say so.

* The App is created and installed by the operator, with his GitHub login,
  through ``tools/gagos_github_app.py create`` (GitHub's manifest flow): he
  clicks "Create" and "Install"; GAGOS asks for no more than it needs.
* Its id, slug and private key go straight into his OS credential store
  (``aios/operations/keystore.py`` LOCAL_ONLY); production is never handed
  them, and nothing prints them.
* For each delivery GAGOS signs a short-lived App JWT (RS256, 9 minutes) and
  exchanges it for an installation token scoped to ONE repository and two
  permissions (contents: write, pull_requests: write), valid one hour. It can
  push a branch and open a PR. It cannot change settings or administer
  anything.
* Merging, honestly (Codex's post-merge review of #566): contents: write lets
  GitHub's merge endpoint accept this token, and master's protection requires
  checks, not reviews, and does not restrict who may push. So GitHub WOULD let
  the App merge a PR whose checks pass. That GAGOS never merges is a rule of
  its code (nothing here or in its delivery calls a merge) and the operator
  merges; making it a GitHub lock is his repository setting to choose.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

API = "https://api.github.com"
#: What GAGOS's App may do, and nothing more.
PERMISSIONS: Mapping[str, str] = {
    "contents": "write",
    "pull_requests": "write",
    "metadata": "read",
}
#: What a delivery token is narrowed to (metadata read is implied).
TOKEN_PERMISSIONS: Mapping[str, str] = {
    "contents": "write",
    "pull_requests": "write",
}


class GitHubAppError(RuntimeError):
    """GAGOS's App is missing, not installed, or GitHub refused."""


def manifest(*, owner: str, repo: str, redirect_url: str) -> dict[str, Any]:
    """The App GitHub's manifest flow creates: private, no webhook, the least
    permissions a delivery needs."""
    return {
        "name": f"GAGOS ({owner})",
        "url": f"https://github.com/{owner}/{repo}",
        "description": (
            "GAGOS's own identity: it pushes a branch and opens a PR for its own "
            "reviewed work. It cannot merge; the operator does."
        ),
        "public": False,
        "redirect_url": redirect_url,
        "hook_attributes": {
            "url": f"https://github.com/{owner}/{repo}",
            "active": False,
        },
        "default_permissions": dict(PERMISSIONS),
        "default_events": [],
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def app_jwt(app_id: str, private_key_pem: str, *, now: float | None = None) -> str:
    """An RS256 JWT for the App, valid 9 minutes (GitHub allows at most 10),
    issued 60 s in the past for clock drift."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    issued = int(now if now is not None else time.time()) - 60
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps({"iat": issued, "exp": issued + 540, "iss": str(app_id)}).encode()
    )
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signing_input = f"{header}.{payload}".encode()
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr,call-arg]
    return f"{header}.{payload}.{_b64url(signature)}"


Http = Callable[..., Any]


def _default_http() -> Http:
    import httpx

    return httpx.request


def _call(
    http: Http, method: str, path: str, *, token: str, scheme: str, json_body=None
):
    response = http(
        method,
        f"{API}{path}",
        headers={
            "Authorization": f"{scheme} {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=json_body,
        timeout=30,
    )
    if response.status_code >= 300:
        raise GitHubAppError(
            f"GitHub {method} {path} -> {response.status_code}: "
            f"{str(response.text)[:300]}"
        )
    return response.json()


@dataclass(frozen=True)
class AppCredentials:
    app_id: str
    slug: str
    private_key_pem: str


#: The keystore names that together are GAGOS's App.
APP_KEYS = (
    "GAGOS_GITHUB_APP_ID",
    "GAGOS_GITHUB_APP_SLUG",
    "GAGOS_GITHUB_APP_PRIVATE_KEY",
)


def stored_credentials(store: Any) -> AppCredentials | None:
    """GAGOS's App from the keystore, or None when it is not (wholly) there:
    ``stored_any`` tells a partly stored App, which is broken, from none."""
    app_id, slug, pem = (store.get(name) for name in APP_KEYS)
    if not (app_id and slug and pem):
        return None
    return AppCredentials(app_id=app_id, slug=slug, private_key_pem=pem)


def stored_any(store: Any) -> bool:
    """Whether any part of GAGOS's App is in the keystore."""
    return any(store.get(name) for name in APP_KEYS)


def installation_token(
    creds: AppCredentials, *, owner: str, repo: str, http: Http | None = None
) -> str:
    """A one-hour token for ONE repository, contents and pull requests only."""
    http = http or _default_http()
    jwt = app_jwt(creds.app_id, creds.private_key_pem)
    installation = _call(
        http, "GET", f"/repos/{owner}/{repo}/installation", token=jwt, scheme="Bearer"
    )
    token = _call(
        http,
        "POST",
        f"/app/installations/{installation['id']}/access_tokens",
        token=jwt,
        scheme="Bearer",
        json_body={"repositories": [repo], "permissions": dict(TOKEN_PERMISSIONS)},
    )
    return str(token["token"])


def bot_identity(creds: AppCredentials, *, http: Http | None = None) -> tuple[str, str]:
    """``(name, email)`` GitHub links to the App's bot user, for GAGOS's commits."""
    http = http or _default_http()
    login = f"{creds.slug}[bot]"
    response = http(
        "GET",
        f"{API}/users/{login}",
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    if response.status_code >= 300:
        raise GitHubAppError(f"no bot user {login}: {response.status_code}")
    return login, f"{response.json()['id']}+{login}@users.noreply.github.com"


def open_pull_request(
    token: str,
    *,
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    http: Http | None = None,
) -> str:
    """Open the PR as GAGOS's App; returns its URL."""
    created = _call(
        http or _default_http(),
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        token=token,
        scheme="token",
        json_body={"title": title, "head": head, "base": base, "body": body},
    )
    return str(created["html_url"])


def git_auth_env(token: str) -> dict[str, str]:
    """Environment that lets ``git push`` to github.com use *token* without it
    appearing in argv, the remote URL or any config file."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    }


__all__ = [
    "API",
    "AppCredentials",
    "GitHubAppError",
    "PERMISSIONS",
    "TOKEN_PERMISSIONS",
    "app_jwt",
    "bot_identity",
    "git_auth_env",
    "installation_token",
    "manifest",
    "open_pull_request",
    "stored_any",
    "stored_credentials",
]
