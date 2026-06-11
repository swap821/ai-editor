import pytest
from training_ground.date_utils import days_between

def test_days_between():
    assert days_between('2023-01-01', '2023-01-10') == 9
    assert days_between('2023-01-10', '2023-01-01') == 9
    assert days_between('2023-01-01', '2023-01-01') == 0