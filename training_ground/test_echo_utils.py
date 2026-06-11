import pytest
from echo_utils import shout_twice

def test_shout_twice():
    assert shout_twice('hello') == 'HELLO!!'
    assert shout_twice('world') == 'WORLD!!'
