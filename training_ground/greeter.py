"""Sandbox breath fixture used to demonstrate a supervised AI-OS repair.

This lives in training_ground/ (the agent's only in-scope writable root), so the
agent can perceive a planted bug, propose an edit_file diff, and — once you
approve — have it written + snapshotted, then verified.
"""


def greet(name):
    return f"Hello, {name}!"
