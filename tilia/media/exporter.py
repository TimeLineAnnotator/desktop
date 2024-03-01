import pydub
from pathlib import Path


def export_audio(
    source_path: Path,
    destination_path: Path,
    start_time: float,
    end_time: float,
) -> None:
    segment = pydub.AudioSegment.from_file(source_path)
    requested_section = segment[start_time * 1000 : end_time * 1000]

    requested_section.export(destination_path, format="ogg")
