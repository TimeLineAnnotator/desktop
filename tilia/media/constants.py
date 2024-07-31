SUPPORTED_AUDIO_FORMATS = ["ogg", "wav"]
CONVERTIBLE_AUDIO_FORMATS = [
    "mp3",
    "aac",
    "m4a",
    "flac",
]  # ffmpeg can probably convert more formats
SUPPORTED_VIDEO_FORMATS = ["mp4", "mkv", "m4a"]
ALL_SUPPORTED_MEDIA_FORMATS = {
    media_format
    for media_format in {
        *SUPPORTED_AUDIO_FORMATS,
        *CONVERTIBLE_AUDIO_FORMATS,
        *SUPPORTED_VIDEO_FORMATS,
    }
}
