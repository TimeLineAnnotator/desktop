# tilia-library

TiLiA Library is a local web interface for querying and editing folders of [TiLiA](https://tilia-app.com) files. It is built on tilia-core and needs neither the TiLiA app nor Qt.

This package is under development and nothing is stable yet.

```
pip install tilia-library
```

## Usage

```
tilia library [FOLDER] [--port N] [--no-browser]
```

Starts the library on 127.0.0.1, on port 8765 or the first free one after it (`--port N` starts from N), prints its address, and opens it in your browser (`--no-browser` doesn't). `FOLDER` is added to the library if it is new. If a library is already running, the command adds `FOLDER` to it and opens the browser there instead of starting a second one.

## Panels

- **Files**: the files of a corpus (a folder), with their fields and timelines. The table sorts and filters.
- **Query**: a query box with results as cards or as a sortable table, an SQL view and CSV export. A double-click plays a result from the file's media, and "Open in TiLiA" opens its file. A query that ends in an action shows a preview of the bulk edit before anything is written.
- **Categories**: the categories of the corpus's labels as chips with their counts, the components in the chosen ones, and edits of them, previewed in the Query tab.
- **Statistics**: the statistics of the Query tab's query (counts, durations, positions in the piece, transitions), as charts and tables.
- **Edit log**: the edits made so far, with undo.

The library reads and edits files only through tilia-core's index, query engine and edit functions, which are still being written. Until they are, its panels say "Not available yet".

## State

`library.toml` (the corpora) and `server.toml` (where the running library can be reached) are kept in the `library` folder of TiLiA's per-user data folder, as `tilia_core.state.state_dir()` returns it, without creating it:

- Linux: `~/.local/share/TiLiA/library` (or under `$XDG_DATA_HOME`)
- macOS: `~/Library/Application Support/TiLiA/library`
- Windows: `%LOCALAPPDATA%\TiLiA\TiLiA\library`

The page loads nothing from the internet. The one exception is YouTube's player, when the media of a result is on YouTube.

## Development

To try the server by hand on fixture data, without the core:

```
python packages/tilia-library/tests/support/serve_fixtures.py [--port N]
```

It prints the address to open in a browser and serves until Ctrl+C. `--change-after S` raises the generation after S seconds, which makes the page show "Files changed — re-run?".

The browser tests drive the page in headless Chromium with Playwright, which is a test dependency only. Install the browser once, then run the tests:

```
uv run --package tilia-library --group browser playwright install chromium
uv run --package tilia-library --group browser pytest packages/tilia-library/tests/browser
```

## License

GNU General Public License, version 3 or later. Source: <https://github.com/TimeLineAnnotator/desktop>
