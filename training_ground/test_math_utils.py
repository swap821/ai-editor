import pytest
from math_utils import clamp

def test_clamp():
    assert clamp(5, 1, 10) == 5
    assert clamp(0, 1, 10) == 1
    assert clamp(11, 1, 10) == 10
    assert clamp(-1, -5, 5) == -1