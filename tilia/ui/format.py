def format_media_time(audio_time: float | str) -> str:
    minutes = str(int(float(audio_time) // 60)).zfill(2)
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    return f"{minutes}:{seconds_and_fraction}"
