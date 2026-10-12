"""The page's side of liveness, run under node with a stand-in DOM."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import tilia_library

JS = Path(tilia_library.__file__).resolve().parent / "web" / "js"
HARNESS = Path(__file__).resolve().parent / "support" / "liveness_harness.mjs"


@pytest.fixture(scope="module")
def shown():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    run = subprocess.run(
        [node, str(HARNESS), str(JS)], capture_output=True, text=True, timeout=30
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_the_notice_shows_when_the_generation_moves(shown):
    assert shown["notice_after_change"] is True


def test_a_failed_rerun_keeps_the_notice_and_shows_the_error(shown):
    assert shown["notice_after_failed_rerun"] is True
    assert "reload failed" in shown["status_after_failed_rerun"]
    assert shown["status_class_after_failed_rerun"] == "error"


def test_a_rerun_that_works_hides_the_notice(shown):
    assert shown["notice_after_good_rerun"] is False


def test_rescanning_clears_when_the_scan_ends(shown):
    assert shown["status_while_scanning"] == "Rescanning…"
    assert shown["status_after_scan_seen_ending"] == ""
    assert shown["status_without_a_scan"] == "Rescanning…"
    assert shown["status_after_last_scan_moved"] == ""
    assert shown["other_status_kept"] == "something else"
