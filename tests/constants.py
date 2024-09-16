from pathlib import Path

EXAMPLE_MEDIA_PATH = str((Path(__file__).parent / "resources" / "example.mp3").resolve()).replace("\\", "/")
EXAMPLE_MEDIA_DURATION = 9.952
EXAMPLE_MEDIA_SCALE_FACTOR = EXAMPLE_MEDIA_DURATION / 100

EXAMPLE_OGG_DURATION = 9.952