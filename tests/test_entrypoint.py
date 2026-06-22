"""P0-6: the ``python -m aios`` entrypoint binds the configured (policy) host/port.

Pins that the canonical launch binds exactly ``config.API_HOST`` / ``config.API_PORT``
— the host the lifespan token-policy validates — so the real bind can't decouple from
the policy (the failure mode the entrypoint exists to prevent).
"""
from __future__ import annotations

import sys
from unittest.mock import patch

from aios import config


def test_entrypoint_binds_configured_host_and_port():
    import aios.__main__ as entry

    with patch("uvicorn.run") as run, patch.object(sys, "argv", ["python -m aios"]):
        entry.main()

    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == "aios.api.main:app"
    assert kwargs["host"] == config.API_HOST
    assert kwargs["port"] == config.API_PORT
    assert kwargs["reload"] is False
