import pytest
from training_ground.stats_utils import moving_average


def test_moving_average_normal_case():
    values = [1, 2, 3, 4, 5]
    window = 2
    result = moving_average(values, window)
    assert result == [1.5, 2.5, 3.5, 4.5]


def test_moving_average_error_case_window_too_small():
    values = [1, 2, 3, 4, 5]
    window = 0
    with pytest.raises(ValueError):
        moving_average(values, window)


def test_moving_average_error_case_window_too_large():
    values = [1, 2, 3, 4, 5]
    window = 6
    with pytest.raises(ValueError):
        moving_average(values, window)