def format_media_time(audio_time: float | str) -> str:
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    minutes = int(float(audio_time) // 60)
    hours = str(minutes // 60) + ":" if minutes >= 60 else ""
    minutes = str(minutes % 60).zfill(2)
    return f"{hours}{minutes}:{seconds_and_fraction}"
