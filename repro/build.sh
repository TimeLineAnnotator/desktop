#!/usr/bin/env bash
# Regenerates the repro bundle for the "video that never loads" fix.
#
#   ./repro/build.sh
#
# yt-ok.tla is written by TiLiA's own CLI, so it comes out of the real
# serializer; yt-missing-video.tla is the same file with media_path pointed at
# a well-formed URL whose video id does not exist. No .tla JSON is written by
# hand.
#
# Paths passed to the CLI must be absolute: outside ENVIRONMENT=prod,
# dirs.setup_dirs chdirs into the tilia package, so a relative `save` lands
# inside tilia/ instead of the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
REPRO="$PWD/repro"

printf '%s\n' \
  'load-media "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --scale-timelines no' \
  'timelines add marker --name "Cues"' \
  'metadata set title "repro - YouTube video loads"' \
  "save $REPRO/yt-ok.tla --overwrite" \
  'quit' | uv run tilia -i cli

uv run python repro/make-missing-video.py
