from tilia.requests import get, Get


def format_media_time(audio_time: float | str, is_playback: bool = True) -> str:
    if is_playback:
        audio_time = float(audio_time) - get(Get.MEDIA_TIMES_PLAYBACK).start
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    minutes = int(float(audio_time) // 60)
    hours = str(minutes // 60) + ":" if minutes >= 60 else ""
    minutes = str(minutes % 60).zfill(2)
    return f"{hours}{minutes}:{seconds_and_fraction}"
