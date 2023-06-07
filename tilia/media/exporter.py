import pydub
from pathlib import Path


def export_audio(
    audio_path: Path,
    dir: Path,
    file_title: str,
    segment_name: str,
    start_time: float,
    end_time: float,
) -> None:
    segment = pydub.AudioSegment.from_file(audio_path)
    requested_section = segment[start_time * 1000 : end_time * 1000]

    path = Path(dir, f"{file_title}_{segment_name}").with_suffix(".ogg")
    requested_section.export(path, format="ogg")
