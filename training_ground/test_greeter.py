"""Verification test for the sandbox breath. Run: pytest test_greeter.py

Plant a bug in greeter.py to demonstrate the repair loop; this test is the
agent's evidence target.
"""
from greeter import greet


def test_greet_includes_name():
    assert greet("Ada") == "Hello, Ada!"
