from tilia.ui.cli.generate_scripts import (
    _get_args_from_filename,
    _get_script_for_folder,
)
import pytest


@pytest.mark.parametrize(
    "filename, kind, expected_args, expected_is_by_time, expected_name",
    [
        (
            "timeline_beat_count_beat-pattern_4_height_20",
            "beat",
            ["--beat-pattern 4", "--height 20"],
            True,
            "timeline_count",
        ),
        (
            "timeline_hrc_hierarchy__height_20_by-time",
            "hrc",
            ["--height 20"],
            True,
            "timeline_hierarchy_",
        ),
        ("timeline_mrk_name_by-measure", "mrk", [], False, "timeline_name"),
    ],
)
def test_get_args_from_filename(
    filename, kind, expected_args, expected_is_by_time, expected_name
):
    args, is_by_time, name = _get_args_from_filename(filename, kind)
    for arg in expected_args:
        assert arg in args
    assert is_by_time == expected_is_by_time
    assert name == expected_name


def test_get_args_from_filename_with_time_and_measure_fails():
    with pytest.raises(
        ValueError, match=r"File name contains both by-time and by-measure."
    ):
        _get_args_from_filename("marker_by-time_by-measure", "marker")


def test_get_script_for_folder(tmpdir):
    duration = 250
    with open(tmpdir.join("set_media_length.txt"), "w") as f:
        f.write(str(duration))

    filenames = [
        "some_media_file.mp3",
        "beat_tlName.csv",
        "metadata.json",
        "set_media_length.txt",
    ]
    output_script_path = _get_script_for_folder(tmpdir.strpath, filenames)

    assert output_script_path == tmpdir.join("script.txt")

    output_script = tmpdir.join("script.txt").read()

    assert output_script_path == tmpdir.join("script.txt")
    assert f'load-media "{tmpdir.join("some_media_file.mp3")}"' in output_script
    assert f"metadata set-media-length {duration}" in output_script
    assert f'metadata import "{tmpdir.join("metadata.json")}"' in output_script
    assert 'timelines add beat --name "tlName"' in output_script
    assert (
        f'timelines import csv beat --target-name "tlName" --file "{tmpdir.join("beat_tlName.csv")}"'
        in output_script
    )
    assert f'save "{tmpdir}' in output_script and '.tla"' in output_script


def test_get_script_for_folder_returns_none_on_no_media(tmpdir):
    filenames = ["beat_tlName.csv", "metadata.json"]
    assert _get_script_for_folder(tmpdir.strpath, filenames) is None


def test_get_script_for_folder_required_beat_file(tmpdir):
    filenames = [
        "some_media.mp4",
        "beat_tlName.csv",
        "metadata.json",
        "marker_tlName2_by-time.csv",
    ]
    assert _get_script_for_folder(tmpdir.strpath, filenames) is not None
    assert "by-time" in tmpdir.join("script.txt").read()

    filenames = [
        "some_media.mp4",
        "beat_tlName.csv",
        "metadata.json",
        "marker_tlName2_by-measure.csv",
    ]
    assert _get_script_for_folder(tmpdir.strpath, filenames) is not None
    assert "by-measure" in tmpdir.join("script.txt").read()
    assert "--reference-tl-name" in tmpdir.join("script.txt").read()

    filenames = ["some_media.mp4", "metadata.json", "marker_tlName2_by-measure.csv"]
    assert _get_script_for_folder(tmpdir.strpath, filenames) is None
