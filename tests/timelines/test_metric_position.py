from tilia.timelines.base.metric_position import MetricPosition, MetricInterval


def test_same_beat_same_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 1, 4) == MetricInterval(1, 0)


def test_same_beat_different_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 1, 3) == MetricInterval(1, 0)


def test_subtrahend_beat_is_larger_same_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 2, 4) == MetricInterval(0, 3)


def test_subtrahend_beat_is_larger_different_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 2, 3) == MetricInterval(0, 3)


def test_result_beat_exceeds_result_measure_count():
    """This can happen in cases where the subtrahend measure is larger than
    the minuend measure"""
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 3, 7) == MetricInterval(0, 5)
