"""Canonical digests used by exact capability bindings."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def payload_digest(payload: Any) -> str:
    """Hash a canonical JSON value so equivalent payloads bind identically."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resource_digest(resource: Any) -> str:
    """Hash a canonical resource descriptor."""
    return payload_digest(resource)
