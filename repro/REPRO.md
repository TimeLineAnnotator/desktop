# Repro bundle — YouTube videos that never load

Per `CLAUDE.md` → *Delivering a fix for human testing*.

Not media-free: the scenario *is* the YouTube player, so `media_path` carries a
YouTube URL. Nothing binary or machine-specific is bundled, so the fixtures
still travel, but the check needs a working internet connection.

| File | `media_path` | Role |
|---|---|---|
| `repro/yt-ok.tla` | `watch?v=dQw4w9WgXcQ` — public, embeddable | the video that loads |
| `repro/yt-missing-video.tla` | `watch?v=zzzzzzzzzzz` — well-formed, no such video | the video that never loads |

Regenerate with `./repro/build.sh` from the repo root. `yt-ok.tla` comes out of
TiLiA's own CLI; `make-missing-video.py` derives the other by swapping
`media_path`. No `.tla` JSON is hand-authored.

## Launch

One-time setup, not part of the launch line — re-running it aborts when the
branch is checked out in another worktree, and `--force` would discard local
edits:

```bash
gh pr checkout <N>
```

Then, from the repo root:

```bash
uv run tilia "$PWD/repro/yt-ok.tla"
```

The path has to be absolute: outside `ENVIRONMENT=prod`, `dirs.setup_dirs`
chdirs into the `tilia` package after `boot()` has parsed the argument, so a
relative path passes validation and then fails to open.

## Acceptance criteria

### The reported bug — invalid URL after a valid one, same session
- **Do:** launch with `yt-ok.tla`, wait for the video to play, then File → Open `yt-missing-video.tla`.
- **Was broken:** no error; the file appears to open while the *previous* video stays loaded and playable, and TiLiA reports the new URL as loaded.
- **Correct:** within about ten seconds an error appears — "Could not load this video. It may have been removed, made private, or the video ID may be wrong." — the old video stops, and the player controls go back to their no-media state.

### Fresh session, video that does not exist
- **Do:** launch with `yt-missing-video.tla` as the first file of the session.
- **Was broken:** YouTube's own `onError` fired here, so an error did appear — but the player still reported the media as loaded.
- **Correct:** the load-failure error above, and no media claimed as loaded.

### The video that does load — check for regressions
- **Do:** launch with `yt-ok.tla` and play it.
- **Was broken:** nothing; this path worked and must keep working.
- **Correct:** the video plays, the timeline's duration matches it, and no error appears — the poll must not turn a slow load into a reported failure.

## Base-branch check

The same two files on `dev` show the broken behavior: the first scenario opens
silently with the old video still playing. The fixtures are branch-agnostic, so
`git switch dev` and relaunch is the whole comparison.

## Fixture lifecycle

Delete `repro/*.tla` before merge. The durable artifacts are `build.sh` and
`make-missing-video.py`; the load-outcome logic is already covered by
`tests/player/test_youtube_player.py`.
