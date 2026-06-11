import pytest
from slug_utils import slugify

def test_slugify():
    assert slugify('Hello World!') == 'hello-world'
    assert slugify('  Leading and trailing spaces  ') == 'leading-and-trailing-spaces'
    assert slugify('Special characters: @#$%^&*()_+') == 'special-characters'