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
gh pr checkout 590
```

Then, from the repo root, one line per fixture:

```bash
uv run tilia "$PWD/repro/yt-ok.tla"
```

```bash
uv run tilia "$PWD/repro/yt-missing-video.tla"
```

The path has to be absolute: outside `ENVIRONMENT=prod`, `dirs.setup_dirs`
chdirs into the `tilia` package after `boot()` has parsed the argument, so a
relative path passes validation and then fails to open.

## Why there are two fresh-session scenarios

YouTube does not report an unplayable video when it is loaded, only when
playback is attempted. The player polls until it holds the requested video and
gives up after about three seconds of the YouTube player answering without it;
page and API start-up do not count. Waiting and clicking play early therefore
reach the same failure by different routes.

## Acceptance criteria

### The reported bug — invalid URL after a valid one, same session
- **Do:** launch with `yt-ok.tla`, wait for the video to load, then File → Open `yt-missing-video.tla`.
- **Was broken:** no error; the file appears to open while the *previous* video stays loaded and playable, and TiLiA reports the new URL as loaded.
- **Correct:** a few seconds after opening, exactly one error — "Could not load this video. It may have been removed, made private, or the video ID may be wrong." The old video stops, the player window closes, and the player controls go back to their no-media state.

### Fresh session, video that does not exist — wait
- **Do:** launch with `yt-missing-video.tla` as the first file of the session and touch nothing.
- **Was broken:** no error until playback was attempted, and the media was reported as loaded throughout.
- **Correct:** the same single error, a few seconds after the player window appears, and no media claimed as loaded.

### Fresh session, video that does not exist — play before the error
- **Do:** launch with `yt-missing-video.tla` and click play inside the player window straight away.
- **Was broken (earlier revision of this PR):** two dialogs for one failure — YouTube's on the click, the load-failure error a few seconds later.
- **Correct:** exactly one dialog, carrying YouTube's own message, and nothing further when the load would have timed out. YouTube's wording for this case (code 2, "…does not have 11 characters…") is misleading; that text is fixed on `fix/youtube-error-messages`, not here.

### After a failure — reopening the player window
- **Do:** after any failure above, reopen the player window from the View menu and click inside it.
- **Was broken (earlier revision of this PR):** the window showed a player that looked usable. After the same-session bug it still held the previous video, and a click played it; after a fresh-session failure a click did nothing and said nothing.
- **Correct:** the window says "No video loaded", and clicking it does nothing.

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
`make-missing-video.py`; the load-outcome logic is covered by
`tests/player/test_youtube_player.py`.
