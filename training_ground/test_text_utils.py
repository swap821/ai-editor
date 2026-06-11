import pytest
from training_ground.text_utils import shout

def test_shout():
    assert shout('hello') == 'HELLO!'
    assert shout('world') == 'WORLD!'