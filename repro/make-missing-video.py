"""Derive yt-missing-video.tla from the CLI-generated yt-ok.tla.

Only media_path and the title change, so the fixture keeps the exact
structure the app writes today.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tilia.constants import YOUTUBE_URL_REGEX  # noqa: E402

REPRO_DIR = Path(__file__).resolve().parent
BASE = REPRO_DIR / "yt-ok.tla"
TARGET = REPRO_DIR / "yt-missing-video.tla"
# Well-formed URL, eleven valid characters, no such video.
URL = "https://www.youtube.com/watch?v=zzzzzzzzzzz"

if not BASE.exists():
    raise SystemExit(f"{BASE} missing -- run ./repro/build.sh")
if not re.match(YOUTUBE_URL_REGEX, URL):
    raise SystemExit(f"{URL!r} does not match YOUTUBE_URL_REGEX")

data = json.loads(BASE.read_text(encoding="utf-8"))
data["media_path"] = URL
data["media_metadata"]["title"] = "repro - YouTube video does not exist"
data["file_path"] = ""  # rewritten by file_manager.open_tla on open
TARGET.write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"wrote {TARGET}")
