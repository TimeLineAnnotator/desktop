from pathlib import Path

import soundfile


def export_audio(
    source_path: Path | str,
    destination_path: Path,
    start_time: float,
    end_time: float,
) -> None:
    if isinstance(source_path, Path):
        source_path = source_path.resolve()

    array, sample_rate = soundfile.read(source_path)
    requested_section = array[
        int(start_time * sample_rate) : int(end_time * sample_rate)
    ]

    soundfile.write(destination_path, requested_section, sample_rate)
