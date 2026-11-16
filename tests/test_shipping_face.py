"""The face that ships (2026-11-16, the operator: "fix it honestly").

* The gateway image could not build from 2026-06-09: the repository's
  .dockerignore leaves frontend/ out, and Dockerfile.frontend copies it. The
  gateway now has its own ignore file.
* tools/shipping_face.py stands in for the gateway's nginx on loopback: the
  image's own files, /api and /health forwarded to the backend, streaming, every
  Set-Cookie kept.
* A journey pins the checkout that serves the face through it.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import httpx
from starlette.testclient import TestClient

from tools import gagos_journeys as gj
from tools import shipping_face as sf

REPO = Path(__file__).resolve().parents[1]


def test_the_gateway_has_its_own_build_context() -> None:
    lines = [
        line.strip()
        for line in (REPO / "Dockerfile.frontend.dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*"
    assert "!frontend" in lines and "!gateway/nginx.conf.template" in lines
    assert {"frontend/node_modules", "frontend/dist"} <= set(lines)
    dockerfile = (REPO / "Dockerfile.frontend").read_text(encoding="utf-8")
    copied = [
        line.split()[1]
        for line in dockerfile.splitlines()
        if line.startswith("COPY ") and "--from" not in line
    ]
    assert copied and all(
        source.startswith("frontend/") or source == "gateway/nginx.conf.template"
        for source in copied
    ), copied
    assert "frontend" in (REPO / ".dockerignore").read_text(encoding="utf-8").split()


class Chunks(httpx.AsyncByteStream):
    """A backend answer arriving in pieces, as the turn's events do (a
    response built from plain bytes is read at once and cannot stream)."""

    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def _site(tmp_path: Path) -> Path:
    html = tmp_path / "html"
    (html / "assets").mkdir(parents=True)
    (html / "index.html").write_text("<html>face</html>", encoding="utf-8")
    (html / "assets" / "index-x.js").write_text("console.log(1)", encoding="utf-8")
    return html


def _client(tmp_path: Path, handler) -> TestClient:
    upstream = httpx.AsyncClient(
        base_url="http://localhost:8000", transport=httpx.MockTransport(handler)
    )
    return TestClient(sf.create_app(_site(tmp_path), upstream))


def test_the_page_its_assets_and_its_own_routes_are_served(tmp_path) -> None:
    client = _client(tmp_path, lambda request: httpx.Response(500))
    assert client.get("/").text == "<html>face</html>"
    assert client.get("/assets/index-x.js").text == "console.log(1)"
    assert client.get("/a/route/of/the/face").text == "<html>face</html>"
    assert client.get("/../../etc/passwd").text == "<html>face</html>"


def test_api_calls_reach_the_backend_with_their_cookies_and_body(tmp_path) -> None:
    seen = {}

    def backend(request: httpx.Request) -> httpx.Response:
        seen.update(
            method=request.method,
            path=request.url.raw_path.decode(),
            cookie=request.headers.get("cookie"),
            origin=request.headers.get("origin"),
            body=request.content,
            host=request.headers.get("host"),
        )
        return httpx.Response(
            201,
            headers=[("set-cookie", "a=1; Path=/"), ("set-cookie", "b=2; Path=/")],
            stream=Chunks(b"event: done\n", b"data: {}\n\n"),
        )

    client = _client(tmp_path, backend)
    answer = client.post(
        "/api/generate?x=1",
        content=b'{"ask": "small"}',
        headers={"cookie": "session=s", "origin": "http://localhost:3000"},
    )
    assert answer.status_code == 201 and answer.content == b"event: done\ndata: {}\n\n"
    assert answer.headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]
    assert seen == {
        "method": "POST",
        "path": "/api/generate?x=1",
        "cookie": "session=s",
        "origin": "http://localhost:3000",
        "body": b'{"ask": "small"}',
        "host": "localhost:8000",
    }


def test_health_is_forwarded_like_the_gateways(tmp_path) -> None:
    client = _client(
        tmp_path,
        lambda request: httpx.Response(
            200, stream=Chunks(b'{"path": "' + request.url.path.encode() + b'"}')
        ),
    )
    assert client.get("/health").json() == {"path": "/health"}


def test_a_journey_pins_the_checkout_serving_the_shipping_face(monkeypatch) -> None:
    class Conn:
        status = "LISTEN"
        laddr = types.SimpleNamespace(port=3000)
        pid = 42

    class Process:
        def __init__(self, pid):
            assert pid == 42

        script = r"C:\ev621\tools\shipping_face.py"

        def cmdline(self):
            return [r"C:\venv\python.exe", self.script, "serve"]

        def cwd(self):
            return r"C:\ev621"

    fake = types.SimpleNamespace(
        CONN_LISTEN="LISTEN",
        Error=Exception,
        net_connections=lambda kind: [Conn()],
        Process=Process,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)
    # Started by its full path, or from the checkout by a relative one
    # (2026-11-16: the relative start was first not recognised).
    for script in (r"C:\ev621\tools\shipping_face.py", "tools/shipping_face.py"):
        Process.script = script
        assert gj.served_tree("http://localhost:3000/") == Path(r"C:\ev621").resolve()
