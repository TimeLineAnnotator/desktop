import pytest

from tilia import ffmpeg


def test_install_ffmpeg():
    ffmpeg.install_ffmpeg()
