#!/usr/bin/env python3
"""The face that ships, served on this laptop against the operator's backend.

The face that ships is the gateway image (``Dockerfile.frontend``): nginx
serving the production build, with ``/api`` forwarded to the backend. A
gateway container cannot call the operator's backend on this laptop: the
backend takes unauthenticated calls from loopback only, and the edge's API
token the gateway would add is his secret. So this stands in for nginx, on
loopback. It serves the exact files of the gateway image, and forwards
``/api`` and ``/health`` to the backend the way the dev face's calls already
reach it.

What differs from the shipped gateway: Python in place of nginx, and no bearer
token added. The page, its CSP (a meta tag in ``index.html``) and every asset
are the image's own bytes, and the backend accepts ``http://localhost:3000``,
the gateway's port (``AIOS_CORS_ORIGINS``'s default).

    python tools/shipping_face.py build              # the gateway image for this commit
    python tools/shipping_face.py serve [--port 3000]

Then a journey runs on it: ``tools/gagos_journeys.py run perf-01 --url
http://localhost:3000/``. The journey records the tree and commit it serves.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: Where the gateway image's files are copied out to, by commit.
SERVED = REPO / "data" / "shipping_face"
#: The backend the face's calls reach on loopback.
BACKEND = "http://localhost:8000"
#: Headers that belong to one connection, never forwarded either way.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


def _docker() -> str:
    found = shutil.which("docker")
    if not found:
        raise SystemExit("docker is not on PATH")
    return found


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argv
        ["git", "-C", str(REPO), *args],  # noqa: S607 - git on PATH, as everywhere here
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def image_tag() -> str:
    """The gateway image for this checkout's commit."""
    return f"aios-gateway:{_git('rev-parse', '--short=12', 'HEAD')}"


def cmd_build(_args: argparse.Namespace) -> int:
    tag = image_tag()
    print(f"building {tag} from Dockerfile.frontend")
    return subprocess.run(  # noqa: S603 - fixed argv
        [_docker(), "build", "-f", "Dockerfile.frontend", "-t", tag, "."],
        cwd=REPO,
        check=False,
    ).returncode


def extract(tag: str) -> Path:
    """The image's served files, copied out once per commit."""
    dest = SERVED / tag.split(":", 1)[1] / "html"
    if (dest / "index.html").is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    docker = _docker()
    name = f"gagos-shipping-face-{tag.split(':', 1)[1]}"
    subprocess.run([docker, "rm", "-f", name], capture_output=True, check=False)  # noqa: S603 - fixed argv
    made = subprocess.run(  # noqa: S603 - fixed argv
        [docker, "create", "--name", name, tag],
        capture_output=True,
        text=True,
        check=False,
    )
    if made.returncode != 0:
        raise SystemExit(
            f"no image {tag}: run `python tools/shipping_face.py build` first\n{made.stderr.strip()}"
        )
    try:
        subprocess.run(  # noqa: S603 - fixed argv
            [docker, "cp", f"{name}:/usr/share/nginx/html", str(dest)], check=True
        )
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, check=False)  # noqa: S603 - fixed argv
    return dest


def create_app(html: Path, client):
    """nginx's three locations (gateway/nginx.conf.template): ``/health`` and
    ``/api/`` forwarded to the backend -- the request body read whole first, as
    nginx buffers it by default, and the answer streamed back unbuffered, as
    its ``proxy_buffering off`` does for the turn's events -- and everything
    else served from *html*, falling back to ``index.html`` for the face's own
    routes."""
    from starlette.applications import Starlette
    from starlette.background import BackgroundTask
    from starlette.responses import FileResponse, StreamingResponse
    from starlette.routing import Route

    root = html.resolve()

    async def forward(request):
        target = request.url.path + (
            f"?{request.url.query}" if request.url.query else ""
        )
        headers = [
            (k, v) for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
        ]
        upstream = client.build_request(
            request.method, target, headers=headers, content=await request.body()
        )
        answer = await client.send(upstream, stream=True)
        response = StreamingResponse(
            answer.aiter_raw(),
            status_code=answer.status_code,
            background=BackgroundTask(answer.aclose),
        )
        # Every header, each Set-Cookie on its own line, as the backend sent them.
        response.raw_headers = [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in answer.headers.multi_items()
            if k.lower() not in HOP_BY_HOP
        ]
        return response

    async def static(request):
        wanted = (root / request.path_params["path"]).resolve()
        if wanted.is_file() and root in wanted.parents:
            return FileResponse(wanted)
        return FileResponse(root / "index.html")

    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    return Starlette(
        routes=[
            Route("/health", forward, methods=methods),
            Route("/api/{rest:path}", forward, methods=methods),
            Route("/{path:path}", static, methods=["GET", "HEAD"]),
        ]
    )


def cmd_serve(args: argparse.Namespace) -> int:
    import httpx
    import uvicorn

    tag = args.image or image_tag()
    html = extract(tag)
    client = httpx.AsyncClient(base_url=args.backend, timeout=None)
    print(
        f"the face that ships ({tag}) on http://localhost:{args.port}/ -> {args.backend}"
    )
    uvicorn.run(
        create_app(html, client), host="127.0.0.1", port=args.port, log_level="warning"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    built = sub.add_parser("build", help="build the gateway image for this commit")
    built.set_defaults(func=cmd_build)
    served = sub.add_parser("serve", help="serve the gateway image's files on loopback")
    served.add_argument("--port", type=int, default=3000)
    served.add_argument("--image", help="a gateway image tag (default: this commit's)")
    served.add_argument("--backend", default=BACKEND)
    served.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
