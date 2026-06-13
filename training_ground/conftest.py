"""Make the agent's auto-verify robust to either import style.

The force-verify-after-write runs ``python -m pytest <sandbox test>`` from the
repo root. Tests that import the sibling module as ``from training_ground.x``
already resolve (the repo root is on the path). But the agent often writes the
natural bare form ``from x import ...`` — which fails *collection* with
ModuleNotFoundError, so the turn records ``unverified`` (an un-collectable check is
never a false pass) and the router gets no evidence to calibrate on.

Putting this sandbox directory on ``sys.path`` lets the bare form resolve too, so
*either* import style collects and the verify yields a real PASS/FAIL — turning the
agent's coding turns into the verified evidence the router learns from. Scope is
unchanged: this only affects how the sandbox's own tests import; it grants no write
access (the executor's scope-lock is independent of import resolution).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
