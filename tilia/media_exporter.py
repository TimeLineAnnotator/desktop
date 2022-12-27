import pydub
from pathlib import Path


def export_audio_segment(
    audio_path: Path,
    dir: Path,
    file_title: str,
    segment_name: str,
    start_time: float,
    end_time: float,
) -> None:

    segment = pydub.AudioSegment.from_file(audio_path)
    requested_section = segment[start_time * 1000 : end_time * 1000]

    requested_section.export(f"{dir}/{file_title}_{segment_name}.ogg", format="ogg")
