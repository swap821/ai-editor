"""The emergency stop reaches learning (plan Phase 0b, containment 3 of 3).

Engaging the stop halted replayed ACTIONS -- the executor refuses them -- but
not LEARNING. The learning red-team reel measured it on master (RT-07): with
the latch engaged, a skill, a lesson, a chat memory and a compiled reflex were
all written. The system kept deciding what to believe and repeat while its
operator had revoked its authority to act, and those beliefs outlive the stop.

Every learning write now asks the latch first and is refused while it is
engaged. The check reuses the canonical controller's ``assert_operational``
rather than reading the latch table itself: this codebase has already paid for
three spellings of the stop rule drifting apart, and this must not be a fourth.

It reads the DURABLE latch under ``config.DATA_DIR``, which is the one the
operator engages, so no store needs a stop handle injected to be frozen. Full
wiring -- injected, `require_stop_wired` at construction, freeze/thaw on the
bus -- is plan Phase 6. Fail-closed: a latch that cannot be read refuses the
write, because "could not tell" is not "not engaged".
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

#: The control a refused learning write names -- the same one that halts
#: actions, because it is the same latch.
LEARNING_FREEZE_CONTROL = "emergency_stop"

_controllers: dict[Path, Any] = {}
_lock = threading.Lock()


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def _latch() -> Any:
    """The canonical controller over the durable latch, read-only in use.

    Constructed with inert hooks: this module only ever READS the latch. The
    hooks run when the stop is ENGAGED, which happens through the operator's
    authenticated route and its own fully-hooked controller, never here.
    """
    from aios import config
    from aios.application.governance.emergency_stop import (
        EmergencyStopController,
        EmergencyStopHooks,
    )

    path = Path(config.DATA_DIR) / "emergency_stop.db"
    with _lock:
        controller = _controllers.get(path)
        if controller is None:
            controller = EmergencyStopController(
                path,
                hooks=EmergencyStopHooks(
                    revoke_capabilities=_noop,
                    cancel_queued_missions=_noop,
                    kill_active_workers=_noop,
                    disable_autonomy=_noop,
                    preserve_evidence=_noop,
                ),
            )
            _controllers[path] = controller
    return controller


def assert_learning_permitted(boundary: str) -> None:
    """Refuse a learning write while the emergency stop is engaged.

    Raises ``EmergencyStopError`` (engaged) or whatever reading the latch
    raises (unreadable) -- both refuse. *boundary* names the write, for the
    operator reading why it did not land.
    """
    from aios.application.governance.emergency_stop import EmergencyStopError

    try:
        _latch().assert_operational()
    except EmergencyStopError as exc:
        raise EmergencyStopError(
            f"{exc} -- learning is frozen too; refused: {boundary}"
        ) from exc
