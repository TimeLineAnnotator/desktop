# Score content

Score files for the tests of scores inside `.tla` files (`test_tla_scores.py`, `test_tla_migrate_scores.py`). The core stores a score's content as text and never parses it, so these files are read as text only. The tests make the other forms they need from them: CRLF line endings, no final newline.

| File | What it is |
| --- | --- |
| `serenade.musicxml` | A short score of our own: two bars for a voice, with Greek lyrics. Its text holds what a score's content must keep exactly: quotes, a backslash and a tab (in its `<words>`), text in Greek, Czech and Japanese, and a letter decomposed (the `a` of `Ständchen` followed by a combining diaeresis, U+0308), which NFC would compose. |
| `serenade.mei` | `serenade.musicxml` converted to MEI by Verovio 6.3.0 (the `verovio` package from PyPI, on Python 3.12), unchanged. Verovio kept the quotes, the backslash, the tab and the decomposed letter; its lines end in LF, with a final newline. |
| `osmd-legacy.svg` | The `svg_data` of the score timeline in `../old/0.7.0.tla`, unchanged, without a final newline: what the migration turns into a legacy score. It is the placeholder `save_with_tilia.py` sets, `<svg xmlns="http://www.w3.org/2000/svg"></svg>`, not a drawing by OSMD; `../old/0.5.15.tla` holds the same. |

## Making the MEI again

Verovio is an optional extra of the core, never a dependency of its tests, so it runs outside the package, in an environment of its own:

```bash
uv run --no-project --python 3.12 --with verovio==6.3.0 python -I to_mei.py serenade.musicxml serenade.mei
```

where `to_mei.py`, kept outside the repository, is:

```python
import sys

import verovio

toolkit = verovio.toolkit()
toolkit.setOptions({"inputFrom": "musicxml"})
if not toolkit.loadFile(sys.argv[1]):
    sys.exit("Verovio couldn't load " + sys.argv[1])
with open(sys.argv[2], "w", encoding="utf-8", newline="") as file:
    file.write(toolkit.getMEI({}))
```

A new run gives the same score, not the same bytes: Verovio gives each element a random `xml:id` and writes the time of the conversion in `isodate`.
