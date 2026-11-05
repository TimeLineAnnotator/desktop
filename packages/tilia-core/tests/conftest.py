import hashlib
import json

import jsonschema
import pytest

from tilia_core import tla
from tilia_core.tla import writer


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
    config.addinivalue_line(
        "markers",
        "writes_outside_the_schema(reason): the test writes a file the format's"
        " schema refuses, on purpose, for the reason given",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-benchmarks"):
        return
    skip = pytest.mark.skip(reason="a benchmark: run it with --run-benchmarks")
    for item in items:
        if item.get_closest_marker("benchmark"):
            item.add_marker(skip)


# Every file the tests write is checked against the format's schema with a
# standard validator (FR-091, SC-009). A test that writes a file the schema
# refuses fails, unless it is marked writes_outside_the_schema; a test so
# marked fails if every file it writes is valid, so that no mark outlives
# its reason.
_VALIDATOR = jsonschema.Draft202012Validator(tla.schema())
_VALID: set[bytes] = set()  # the digests of files found valid, checked once


def _schema_error(data):
    """The first thing the schema refuses in a written file, or None."""
    digest = hashlib.sha256(data).digest()
    if digest in _VALID:
        return None
    error = jsonschema.exceptions.best_match(_VALIDATOR.iter_errors(json.loads(data)))
    if error is None:
        _VALID.add(digest)
        return None
    return f"{error.json_path}: {error.message}"


@pytest.fixture(autouse=True)
def written_files_are_valid(request, monkeypatch):
    written = []
    write = writer.canonical_bytes
    write_checked = writer.checked_bytes

    def recorded(doc):
        data = write(doc)
        written.append(data)
        return data

    def recorded_once_checked(doc, **kwargs):
        # What write writes: the canonical bytes, once the reader's checks
        # have let them through.
        data = write_checked(doc, **kwargs)
        written.append(data)
        return data

    # The writer's own callers look it up in its module, the tests in tla's.
    monkeypatch.setattr(writer, "canonical_bytes", recorded)
    monkeypatch.setattr(tla, "canonical_bytes", recorded)
    monkeypatch.setattr(writer, "checked_bytes", recorded_once_checked)
    yield
    errors = [error for data in written if (error := _schema_error(data))]
    if request.node.get_closest_marker("writes_outside_the_schema") is None:
        if errors:
            pytest.fail(f"wrote a file the format's schema refuses: {errors[0]}")
    elif not errors:
        pytest.fail(
            "marked writes_outside_the_schema, but every file it wrote is valid:"
            " remove the mark"
        )
