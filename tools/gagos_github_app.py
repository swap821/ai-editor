#!/usr/bin/env python3
"""Give GAGOS its own GitHub identity (the operator's act). aios/operations/github_app.py.

  create   GitHub's manifest flow, in YOUR browser and with YOUR GitHub login:
           a page opens with GAGOS's App filled in (private, no webhook;
           contents write, pull requests write, metadata read). You click
           "Create GitHub App"; GitHub hands this process the App's id and
           private key, which go straight into your Windows Credential Manager
           (GAGOS/GAGOS_GITHUB_APP_*). Nothing is printed. Then the install
           page opens: choose "Only select repositories" -> ai-editor.
  status   whether the App is stored and installed on this repository (it
           mints a token to find out, and prints no secret).

Run it yourself, in your own terminal: creating an identity and granting it
access is the operator's decision, never an agent's.
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios.operations import github_app as gha  # noqa: E402
from aios.operations.keystore import default_keystore  # noqa: E402


def owner_repo() -> tuple[str, str]:
    url = subprocess.run(
        ["git", "-C", str(REPO), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    path = url.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")
    owner, repo = path.split("/")[:2]
    return owner, repo


def _serve_manifest_flow(manifest_for: callable, timeout_s: float) -> str:
    """Serve the auto-submitting form, wait for GitHub's redirect, return the code."""
    state = secrets.token_urlsafe(24)
    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                redirect = f"http://127.0.0.1:{self.server.server_address[1]}/callback"
                form = html.escape(json.dumps(manifest_for(redirect)), quote=True)
                page = (
                    "<!doctype html><meta charset=utf-8><title>GAGOS GitHub App</title>"
                    "<p>Creating GAGOS's GitHub App with your GitHub login...</p>"
                    f'<form id=f method=post action="https://github.com/settings/apps/new?state={state}">'
                    f'<input type=hidden name=manifest value="{form}"></form>'
                    "<script>document.getElementById('f').submit()</script>"
                )
                body = page.encode()
            elif parsed.path == "/callback":
                query = urllib.parse.parse_qs(parsed.query)
                if query.get("state", [""])[0] != state:
                    body = b"state mismatch: nothing was stored"
                else:
                    result["code"] = query.get("code", [""])[0]
                    body = b"GAGOS's App was created. You can close this tab."
                done.set()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"opening {url} in your browser (it forwards to github.com)")
        webbrowser.open(url)
        if not done.wait(timeout_s) or not result.get("code"):
            raise gha.GitHubAppError("no App was created (timed out or state mismatch)")
        return result["code"]
    finally:
        server.shutdown()


def cmd_create(args: argparse.Namespace) -> int:
    if not sys.stdin.isatty():
        print(
            "refused: creating GAGOS's GitHub identity is the operator's act; "
            "run this in your own terminal"
        )
        return 2
    store = default_keystore()
    if gha.stored_credentials(store) and not args.replace:
        print(
            "GAGOS's App is already stored; `status` checks it, `create --replace` replaces it"
        )
        return 0
    owner, repo = owner_repo()
    code = _serve_manifest_flow(
        lambda redirect: gha.manifest(owner=owner, repo=repo, redirect_url=redirect),
        args.timeout,
    )
    import httpx

    response = httpx.post(
        f"{gha.API}/app-manifests/{code}/conversions",
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    if response.status_code >= 300:
        print(f"GitHub refused the conversion: {response.status_code}")
        return 2
    app = response.json()
    store.set("GAGOS_GITHUB_APP_ID", str(app["id"]))
    store.set("GAGOS_GITHUB_APP_SLUG", str(app["slug"]))
    store.set("GAGOS_GITHUB_APP_PRIVATE_KEY", str(app["pem"]))
    print(
        f"created and stored GAGOS's App '{app['slug']}' (id {app['id']}); key not shown"
    )
    install = f"https://github.com/apps/{app['slug']}/installations/new"
    print(f"now install it: choose 'Only select repositories' -> {repo}\n  {install}")
    webbrowser.open(install)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = default_keystore()
    creds = gha.stored_credentials(store)
    if creds is None:
        print(
            "GAGOS has no GitHub App yet: run `python tools/gagos_github_app.py create`"
        )
        return 1
    owner, repo = owner_repo()
    try:
        gha.installation_token(creds, owner=owner, repo=repo)
    except gha.GitHubAppError as exc:
        print(f"App '{creds.slug}' is stored but cannot act on {owner}/{repo}: {exc}")
        return 1
    print(f"App '{creds.slug}' is installed on {owner}/{repo}: GAGOS opens its own PRs")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("--replace", action="store_true")
    c.add_argument("--timeout", type=float, default=900)
    c.set_defaults(func=cmd_create)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
