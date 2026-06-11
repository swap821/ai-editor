import pytest
from list_utils import dedupe
def test_dedupe():
    assert dedupe([1, 2, 2, 3, 4, 4]) == [1, 2, 3, 4]
    assert dedupe(['a', 'b', 'a', 'c']) == ['a', 'b', 'c']
    assert dedupe([]) == []