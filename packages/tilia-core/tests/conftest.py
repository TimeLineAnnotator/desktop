import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-benchmarks",
        action="store_true",
        default=False,
        help="also run the speed benchmarks, which are skipped otherwise",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "benchmark: a speed benchmark, run only with --run-benchmarks"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-benchmarks"):
        return
    skip = pytest.mark.skip(reason="a benchmark: run it with --run-benchmarks")
    for item in items:
        if "benchmark" in item.keywords:
            item.add_marker(skip)
