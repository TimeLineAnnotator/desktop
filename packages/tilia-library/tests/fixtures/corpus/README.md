# The library's test folder

Real `.tla` files for the tests that run `CoreBackend` on tilia-core's index. The tests open this folder in place: the index lives in memory, so nothing is written here.

| File | What it is for |
| --- | --- |
| `every-kind.tla` | The current format: every timeline kind, two beat timelines, metadata at every level, and labels in German, Portuguese, Greek, Chinese, Hebrew and emoji. A copy of tilia-core's golden file `tests/tla/golden/every-kind.tla` (made by `make_golden.py` there). |
| `0.0.96.tla` | A file saved by TiLiA 0.0.96 (slider, hierarchy, marker and beat timelines). A copy of tilia-core's `tests/tla/old/0.0.96.tla`. |
| `0.5.15.tla` | A file saved by TiLiA 0.5.15 (every kind of that version, harmony, PDF, AudioWave and score among them). A copy of tilia-core's `tests/tla/old/0.5.15.tla`. |
| `0.7.0.tla` | A file saved by TiLiA 0.7.0 (every kind of that version, the range timeline among them). A copy of tilia-core's `tests/tla/old/0.7.0.tla`. |
| `not-json.tla` | Not valid JSON: the index lists it as unreadable, with the line. Written by hand, as no version of TiLiA writes such a file. |

The hierarchies of the four readable files give sequences (`Exposição THEN Development` matches in each of the three old files) and the four statistics tables. The media the files name aren't here.

`tests/tla/old/README.md` in tilia-core says how the old files were made. To change a copy, change the original and copy it again.
