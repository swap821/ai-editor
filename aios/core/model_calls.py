"""Every model call, counted where it leaves the process: inside the gateway or not.

The one-gateway property ("every model call passes organ 32's gateway") was
enforced only at CONSTRUCTION -- tests/architecture/test_intelligence_boundary.py
keeps provider classes out of application code -- and asserted in prose for
CALLS. Nothing counted the calls. This module does:

* each provider adapter (``aios/core/{llm,bedrock,gemini,openai_compat,
  anthropic_direct}.py``) calls :func:`observe` once per model request, at the
  point the request is about to leave -- for a stream, when the stream starts;
* each gateway entrance (``aios/application/intelligence/gateway.py``) runs the
  caller's model call inside :func:`gateway_scope` / :func:`scoped_iter`, so an
  observed call knows which entrance it came through, or that it came through
  none;
* every observation is appended to ``<data>/model_calls/<UTC date>.jsonl`` --
  provider, model, method, entrance (``null`` = outside the gateway), the
  calling site, pid. No prompt, no output, no key. The production scoreboard
  reads these files (``tools/production_readiness.py``, ``one_gateway``).

It also REFUSES (2026-10-29): a production call that came through no entrance
raises :class:`UngatedModelCall` in :func:`observe`, before the adapter sends
anything, and is recorded with ``"refused": true``. "Every model call through
the one gateway" then holds by construction, not only as far as a drive
reached (docs/ONE_GATEWAY.md). ``AIOS_GATEWAY_ENFORCE=0`` turns refusing off
and leaves measuring on. Production means the scoreboard's rule,
:func:`judged_stack`: some frame on the call's stack is outside ``tools/`` and
``tests/``. An exempt program's own process is not refused unless asked to
(:func:`enforcing`); its calls are still recorded and judged. The switch and
both exemptions are defined behind the freeze, in ``aios/security/limits.py``.

Scope is a context variable, so it follows the code that runs a model call,
not the thread that happens to hold it: a provider call made in a worker
thread the gateway spawned would read as ungated (over-reporting, the safe
direction), and a consumer's code between stream chunks never runs "inside"
the gateway, because :func:`scoped_iter` holds the scope only while the stream
itself is advancing.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, TypeVar

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

#: The gateway entrance the current code is running inside, or None.
_ENTRANCE: ContextVar[Optional[str]] = ContextVar("aios_gateway_entrance", default=None)

#: Plumbing between a caller and the network. The calling SITE is the first
#: frame outside these: the code that asked for the model call.
_PLUMBING = (
    "aios/core/model_calls.py",
    "aios/core/llm.py",
    "aios/core/bedrock.py",
    "aios/core/gemini.py",
    "aios/core/openai_compat.py",
    "aios/core/anthropic_direct.py",
    "aios/core/vertex_maas.py",
    "aios/core/failover.py",
    "aios/application/intelligence/gateway.py",
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
#: The interpreter's own install: a virtualenv's root (``sys.prefix``), the
#: base interpreter and its standard library. Found 2026-10-29 by a review: the
#: README's install puts ``.venv`` INSIDE the repository, so pytest's own frames
#: (``.venv/Lib/site-packages/_pytest/...``) read as repository code outside
#: ``tests/``, every test-made call was judged production, and the gateway
#: refused it (28 tests, 42 across the gate). It failed closed, so nothing got
#: through, but the README's layout ran red while CI, which installs outside
#: the repository, ran green. Installed code is never the repository's own.
#: Only an install INSIDE the repository needs naming: anything outside it is
#: not repository code already.
_INSTALL_ROOTS = tuple(
    root
    for root in {
        Path(p).resolve() for p in (sys.prefix, sys.base_prefix, sys.exec_prefix) if p
    }
    if root != _REPO_ROOT and root.is_relative_to(_REPO_ROOT)
)
RETENTION = timedelta(days=30)

_LOCK = threading.Lock()
_COUNTS: Counter[tuple[str, str, str, Optional[str], str]] = Counter()
_WRITE_FAILED = False


@contextmanager
def gateway_scope(entrance: str) -> Iterator[None]:
    """Mark the model call made inside this block as coming through *entrance*."""
    token = _ENTRANCE.set(entrance)
    try:
        yield
    finally:
        _ENTRANCE.reset(token)


def scoped_iter(entrance: str, start: Callable[[], Iterable[_T]]) -> Iterator[_T]:
    """Iterate ``start()`` with the scope held only while the stream advances.

    A provider stream issues its request when first advanced, so the scope must
    be live then -- and NOT while the consumer handles a chunk, or the
    consumer's own calls would be credited to the gateway. Setting and
    resetting around each step also keeps every reset in the context its set
    ran in, which a ``with`` held across ``yield`` cannot promise.
    """
    iterator: Optional[Iterator[_T]] = None
    while True:
        token = _ENTRANCE.set(entrance)
        try:
            if iterator is None:
                iterator = iter(start())
            item = next(iterator)
        except StopIteration:
            return
        finally:
            _ENTRANCE.reset(token)
        yield item


def current_entrance() -> Optional[str]:
    return _ENTRANCE.get()


# Who is judged and who is exempt is decided behind the freeze
# (aios/security/limits.py: GATEWAY_ENFORCE, GATEWAY_UNJUDGED_SITES,
# GATEWAY_EXEMPT_PROGRAMS), and read here through aios.config at call time.


def judged(site: str) -> bool:
    """Is a call from *site* production? Code outside ``tools/`` and
    ``tests/`` is, code outside the repository too."""
    from aios import config

    return not str(site or "").startswith(tuple(config.GATEWAY_UNJUDGED_SITES))


def judged_stack(stack: Sequence[str]) -> bool:
    """Is a call with this calling stack production? Yes if ANY frame on it
    is: production code that reaches a model through a tool's helper is
    still production, so a call cannot be passed off as a tool's by where
    its innermost frame happens to live. No repo frame at all is production.
    The one rule for the scoreboard and for refusing."""
    return not stack or any(judged(frame) for frame in stack)


class UngatedModelCall(RuntimeError):
    """A production model call that came through no gateway entrance, refused
    before the adapter sent it."""


def measurement_process() -> bool:
    """Is this process an exempt program (``tools/`` or ``scripts/`` run as
    the main program)?"""
    from aios import config

    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    rel = _relative(path) if path else None
    return bool(rel) and str(rel).startswith(tuple(config.GATEWAY_EXEMPT_PROGRAMS))


def enforcing() -> bool:
    """Are ungated production calls refused in this process?

    ``AIOS_GATEWAY_ENFORCE`` unset (or unrecognised): everywhere except an
    exempt program's own process. Several tools hand a raw client to
    production code on purpose (the payoff harness's teacher, the clerk
    benchmark); there, refusing would break the measurement and protect
    nothing, and the calls are still recorded and judged. ``1``: there too.
    ``0``: nowhere (still recorded).
    """
    from aios import config

    setting = config.GATEWAY_ENFORCE
    if setting is not None:
        return bool(setting)
    return not measurement_process()


def _relative(filename: str) -> Optional[str]:
    # "<frozen runpy>", "<string>", "<stdin>": no file at all. Resolved, they
    # would land under the working directory and read as repo frames.
    if not filename or filename.startswith("<"):
        return None
    try:
        path = Path(filename).resolve()
        rel = path.relative_to(_REPO_ROOT)
        if "site-packages" in rel.parts or any(
            path.is_relative_to(root) for root in _INSTALL_ROOTS
        ):
            return None
        return rel.as_posix()
    except (ValueError, OSError):
        return None


#: How many callers a record keeps, innermost first.
STACK_DEPTH = 12


def calling_stack(depth: int = STACK_DEPTH) -> list[str]:
    """``path:function`` of the repo frames outside the plumbing, innermost
    first: the code that asked for the model call, then what called it."""
    stack: list[str] = []
    frame = sys._getframe(1)
    while frame is not None and len(stack) < depth:
        rel = _relative(frame.f_code.co_filename)
        if rel is not None and rel not in _PLUMBING:
            stack.append(f"{rel}:{frame.f_code.co_name}")
        frame = frame.f_back
    return stack


def calling_site() -> str:
    """``path:function`` of the first repo frame outside the plumbing."""
    stack = calling_stack(1)
    return stack[0] if stack else "outside-repo"


def _ledger_dir() -> Path:
    from aios import config

    return Path(config.DATA_DIR) / "model_calls"


def _append(record: dict[str, Any], now: datetime) -> None:
    global _WRITE_FAILED
    directory = _ledger_dir()
    path = directory / f"{now.date().isoformat()}.jsonl"
    try:
        new_day = not path.exists()
        directory.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if new_day:
            _prune(directory, now)
    except OSError as exc:
        # A lost record under-counts; it never blocks the model call. Said
        # once, loudly, so a silent ledger cannot read as a clean one.
        if not _WRITE_FAILED:
            _LOGGER.warning("model-call ledger write failed (%s): %s", path, exc)
        _WRITE_FAILED = True


def _prune(directory: Path, now: datetime) -> None:
    cutoff = (now - RETENTION).date().isoformat()
    for old in directory.glob("*.jsonl"):
        if old.stem < cutoff:
            try:
                old.unlink()
            except OSError:
                pass


def observe(provider: str, model: str, method: str) -> None:
    """Record one model request about to leave the process, and refuse it
    (:class:`UngatedModelCall`) when it is production and came through no
    entrance, while enforcing."""
    now = datetime.now(timezone.utc)
    entrance = _ENTRANCE.get()
    # The whole stack decides whether the call is production; the record
    # keeps the innermost STACK_DEPTH frames.
    full = calling_stack(depth=sys.getrecursionlimit())
    stack = full[:STACK_DEPTH]
    site = stack[0] if stack else "outside-repo"
    production = judged_stack(full)
    refused = entrance is None and production and enforcing()
    record: dict[str, Any] = {
        "ts": now.isoformat(),
        "provider": provider,
        "model": model,
        "method": method,
        "entrance": entrance,
        "site": site,
        "stack": stack,
        "judged": production,
        "pid": os.getpid(),
    }
    if refused:
        record["refused"] = True
    with _LOCK:
        _COUNTS[(provider, model, method, entrance, site)] += 1
        _append(record, now)
    if refused:
        _LOGGER.error(
            "model call refused: %s asked %s for a model through no gateway "
            "entrance (AIOS_GATEWAY_ENFORCE)",
            site,
            provider,
        )
        raise UngatedModelCall(
            f"{site} asked {provider} for a model call through no gateway "
            "entrance; it was refused before it left (docs/ONE_GATEWAY.md, "
            "AIOS_GATEWAY_ENFORCE)"
        )


def counts() -> Counter[tuple[str, str, str, Optional[str], str]]:
    """This process's observations: (provider, model, method, entrance, site)."""
    with _LOCK:
        return Counter(_COUNTS)


def read_ledger(data_dir: Path, since: datetime) -> list[dict[str, Any]]:
    """Every recorded call at or after *since*, from ``<data_dir>/model_calls``.

    A line that does not parse is returned as ``{"unreadable": <line>}`` rather
    than dropped: the reader decides what a damaged ledger means.
    """
    directory = Path(data_dir) / "model_calls"
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        if path.stem < since.date().isoformat():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                records.append({"unreadable": line[:200]})
                continue
            try:
                stamp = datetime.fromisoformat(str(record["ts"]))
            except (KeyError, ValueError):
                records.append({"unreadable": line[:200]})
                continue
            if stamp >= since:
                records.append(record)
    return records


__all__ = [
    "RETENTION",
    "UngatedModelCall",
    "calling_site",
    "calling_stack",
    "counts",
    "current_entrance",
    "enforcing",
    "gateway_scope",
    "judged",
    "judged_stack",
    "measurement_process",
    "observe",
    "read_ledger",
    "scoped_iter",
]
