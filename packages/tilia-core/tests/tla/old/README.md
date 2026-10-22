# Files from older TiLiA versions

One file per TiLiA version whose files have a shape of their own, saved by that version where it still runs. The tests read each one through the migration.

`file_path`, `media_path` and PDF paths are rewritten to a neutral user's folder, `C:/Users/user/Documents/TiLiA`. Each file is listed here with the TiLiA version that saved it, where it came from, and its license when it isn't this repository's.

| File | Saved by | Source |
| --- | --- | --- |
| `0.0.96.tla` | TiLiA 0.0.96 | Made with `save_with_tilia_0_0_96.py`: every timeline kind of that version (slider, hierarchy, marker, beat), with `display_position`, kinds spelled `HIERARCHY_TIMELINE`, and hierarchies' `parent` and `children`. |
| `0.0.96-saved-by-0.7.0.tla` | TiLiA 0.7.0 | `0.0.96.tla` opened and saved again without an edit, with `save_with_tilia.py resave`. |
| `0.5.15.tla` | TiLiA 0.5.15 | Made with `save_with_tilia.py new`: every timeline kind of that version (slider, hierarchy, marker, beat, harmony, PDF, AudioWave, score). |
| `0.5.15-saved-by-0.7.0.tla` | TiLiA 0.7.0 | `0.5.15.tla` opened and saved again without an edit, with `save_with_tilia.py resave`. |
| `0.5.15.0-many-beats.tla` | TiLiA 0.5.15 | TiLiA's own test file `tests/resources/tla/many_beats.tla`: one beat timeline of 1000 beats, with its version written `0.5.15.0`. |
| `0.6.0-s4-10.tla` | TiLiA 0.6.0 | `tilia/10.tla` of the S4 Dataset v0.1.0 (<https://github.com/FelipeDefensor/s4-dataset>), by Felipe Martins, licensed under CC BY 4.0 (<https://creativecommons.org/licenses/by/4.0/>), unchanged. |
| `0.7.0.tla` | TiLiA 0.7.0 | Made with `save_with_tilia.py new`: every timeline kind of that version, the range timeline among them. |

The files made here were saved on Windows, so their lines end in CRLF, as TiLiA wrote them there; those of the S4 file and of the many beats end in LF.

## Making them again

Each version runs from its own copy of the repository at its tag, in its own virtual environment: Python 3.12 for 0.7.0, 3.11 for 0.5.15 (PyQt6 6.6.0), and 3.10 for 0.0.96, which needs `pandas pygame python_vlc appdirs tomlkit pydub` and Tk. The scripts keep TiLiA's settings in a temporary file, never in the user's own, and start no autosaver.

```bash
git archive v0.7.0 | tar -x -C ../tilia-0.7.0    # and likewise for v0.5.15 and v0.0.96
cd ../tilia-0.7.0 && uv venv --python 3.12 && uv pip install -e .
```

With a short audio file `sonata.ogg` (TiLiA's `tests/resources/example.ogg`, about 10 seconds) and a PDF `score.pdf` in an empty folder `out`, from this folder:

```bash
export GEN_MEDIA=out/sonata.ogg GEN_PDF=out/score.pdf
python-0.0.96 save_with_tilia_0_0_96.py ../tilia-0.0.96 out/0.0.96.tla
python-0.7.0 save_with_tilia.py resave out/0.0.96.tla out/0.0.96-saved-by-0.7.0.tla
python-0.5.15 save_with_tilia.py new out/0.5.15.tla
python-0.7.0 save_with_tilia.py resave out/0.5.15.tla out/0.5.15-saved-by-0.7.0.tla
python-0.7.0 save_with_tilia.py new out/0.7.0.tla
python save_with_tilia.py neutral out .
```

where `python-X` is the interpreter of version X's environment. The media and the PDF exist while the files are saved, so that TiLiA 0.7.0 keeps their paths when it opens a file; `neutral` then rewrites the paths of `out` and copies the files here.

A new run gives the same content, not always the same bytes: TiLiA 0.0.96 writes components in an order that changes from run to run, TiLiA 0.7.0 gives range rows random ids, and the hashes TiLiA stores cover the paths before they are rewritten.
