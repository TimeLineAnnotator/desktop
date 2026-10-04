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

Starts the library and opens it in your browser. `FOLDER` is added to the library if it is new. If a library is already running, the command adds `FOLDER` to it and opens the browser there instead of starting a second one. The library's corpora are kept in `library.toml` in TiLiA's per-user state folder.

## Development

To try the server by hand on fixture data, without the core:

```
python packages/tilia-library/tests/support/serve_fixtures.py [--port N]
```

It prints the address to open in a browser and serves until Ctrl+C.

## License

GNU General Public License, version 3 or later. Source: <https://github.com/TimeLineAnnotator/desktop>
