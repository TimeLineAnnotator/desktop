"""What the index stores beside a file's own values.

Pure functions over plain data: the parent of a hierarchy unit, the end of a
chord or key, the key in force at a chord, the labels and properties of
harmony components, categories, colours and field names.
"""

import re
from collections.abc import Sequence
from typing import Any

from tilia_core import harmony
from tilia_core.labels import LabelGrammar

EPS = 1e-6

C_MAJOR: dict[str, Any] = {"step": 0, "accidental": 0, "type": "major"}
"""The mode TiLiA reads a chord with no key before it in."""


def hierarchy_structure(
    units: Sequence[tuple[str, int, float, float]],
) -> dict[str, tuple[str | None, int]]:
    """For each unit ``(id, level, start, end)`` of one hierarchy timeline,
    ``id -> (parent id, depth)``.

    The parent is the unit on a higher level whose span holds this one (with
    1e-6 s of slack), the smallest by (level, length); the file stores no
    links. Depth is 1 for a unit without parent.
    """
    parents: dict[str, str | None] = {}
    for uid, level, start, end in units:
        best: tuple[tuple[int, float], str] | None = None
        for pid, p_level, p_start, p_end in units:
            if pid == uid or p_level <= level:
                continue
            if p_start <= start + EPS and p_end >= end - EPS:
                key = (p_level, p_end - p_start)
                if best is None or key < best[0]:
                    best = (key, pid)
        parents[uid] = best[1] if best else None

    depths: dict[str, int] = {}

    def depth(uid: str) -> int:
        if uid not in depths:
            parent = parents[uid]
            depths[uid] = 1 if parent is None else depth(parent) + 1
        return depths[uid]

    return {uid: (parents[uid], depth(uid)) for uid in parents}


def implied_spans(starts: Sequence[float], file_end: float) -> list[float]:
    """The end of each point in ``starts`` (sorted): the next start, and for
    the last one ``max(file_end, its start)``."""
    ends = list(starts[1:])
    if starts:
        ends.append(max(file_end, starts[-1]))
    return ends


def key_in_force(
    chord_starts: Sequence[float], key_starts: Sequence[float]
) -> list[int | None]:
    """Per chord, the index of the last key starting at or before it (with
    1e-6 s of slack), or None before the first key. Both sequences are sorted."""
    result: list[int | None] = []
    k = -1
    for start in chord_starts:
        while k + 1 < len(key_starts) and key_starts[k + 1] <= start + EPS:
            k += 1
        result.append(k if k >= 0 else None)
    return result


def chord_fields(chord: dict, key: dict | None) -> dict:
    """The properties of a chord read in ``key`` (C major when it has none),
    plus ``label``, the text TiLiA shows for the chord's ``display_mode``:
    ``custom`` its custom text, ``roman`` its Roman numeral (its symbol when it
    has none), anything else (``letter``, TiLiA's default) its symbol.
    ``key`` of the result is the key in force's label, None without one."""
    props = harmony.chord_props(chord, key or C_MAJOR)
    if key is None:
        props["key"] = None
    mode = chord.get("display_mode")
    if mode == "custom":
        label = chord.get("custom_text") or ""
    elif mode == "roman":
        label = props["roman"] or props["symbol"] or ""
    else:
        label = props["symbol"] or ""
    props["label"] = label
    return props


def key_fields(mode: dict) -> dict:
    """The properties of a key, plus ``label``, its ``key``."""
    props = harmony.key_props(mode)
    props["label"] = props["key"]
    return props


def categories(label: str, grammar: LabelGrammar) -> tuple[str, ...]:
    """The categories of ``label`` under ``grammar``."""
    return grammar.categories(label)


# The 148 SVG colour names (CSS Color Module Level 4, the ones QColor reads).
_CSS = dict(
    pair.split(":")
    for pair in (
        "aliceblue:f0f8ff antiquewhite:faebd7 aqua:00ffff aquamarine:7fffd4 "
        "azure:f0ffff beige:f5f5dc bisque:ffe4c4 black:000000 "
        "blanchedalmond:ffebcd blue:0000ff blueviolet:8a2be2 brown:a52a2a "
        "burlywood:deb887 cadetblue:5f9ea0 chartreuse:7fff00 chocolate:d2691e "
        "coral:ff7f50 cornflowerblue:6495ed cornsilk:fff8dc crimson:dc143c "
        "cyan:00ffff darkblue:00008b darkcyan:008b8b darkgoldenrod:b8860b "
        "darkgray:a9a9a9 darkgreen:006400 darkgrey:a9a9a9 darkkhaki:bdb76b "
        "darkmagenta:8b008b darkolivegreen:556b2f darkorange:ff8c00 "
        "darkorchid:9932cc darkred:8b0000 darksalmon:e9967a "
        "darkseagreen:8fbc8f darkslateblue:483d8b darkslategray:2f4f4f "
        "darkslategrey:2f4f4f darkturquoise:00ced1 darkviolet:9400d3 "
        "deeppink:ff1493 deepskyblue:00bfff dimgray:696969 dimgrey:696969 "
        "dodgerblue:1e90ff firebrick:b22222 floralwhite:fffaf0 "
        "forestgreen:228b22 fuchsia:ff00ff gainsboro:dcdcdc ghostwhite:f8f8ff "
        "gold:ffd700 goldenrod:daa520 gray:808080 green:008000 "
        "greenyellow:adff2f grey:808080 honeydew:f0fff0 hotpink:ff69b4 "
        "indianred:cd5c5c indigo:4b0082 ivory:fffff0 khaki:f0e68c "
        "lavender:e6e6fa lavenderblush:fff0f5 lawngreen:7cfc00 "
        "lemonchiffon:fffacd lightblue:add8e6 lightcoral:f08080 "
        "lightcyan:e0ffff lightgoldenrodyellow:fafad2 lightgray:d3d3d3 "
        "lightgreen:90ee90 lightgrey:d3d3d3 lightpink:ffb6c1 "
        "lightsalmon:ffa07a lightseagreen:20b2aa lightskyblue:87cefa "
        "lightslategray:778899 lightslategrey:778899 lightsteelblue:b0c4de "
        "lightyellow:ffffe0 lime:00ff00 limegreen:32cd32 linen:faf0e6 "
        "magenta:ff00ff maroon:800000 mediumaquamarine:66cdaa "
        "mediumblue:0000cd mediumorchid:ba55d3 mediumpurple:9370db "
        "mediumseagreen:3cb371 mediumslateblue:7b68ee "
        "mediumspringgreen:00fa9a mediumturquoise:48d1cc "
        "mediumvioletred:c71585 midnightblue:191970 mintcream:f5fffa "
        "mistyrose:ffe4e1 moccasin:ffe4b5 navajowhite:ffdead navy:000080 "
        "oldlace:fdf5e6 olive:808000 olivedrab:6b8e23 orange:ffa500 "
        "orangered:ff4500 orchid:da70d6 palegoldenrod:eee8aa palegreen:98fb98 "
        "paleturquoise:afeeee palevioletred:db7093 papayawhip:ffefd5 "
        "peachpuff:ffdab9 peru:cd853f pink:ffc0cb plum:dda0dd "
        "powderblue:b0e0e6 purple:800080 rebeccapurple:663399 red:ff0000 "
        "rosybrown:bc8f8f royalblue:4169e1 saddlebrown:8b4513 salmon:fa8072 "
        "sandybrown:f4a460 seagreen:2e8b57 seashell:fff5ee sienna:a0522d "
        "silver:c0c0c0 skyblue:87ceeb slateblue:6a5acd slategray:708090 "
        "slategrey:708090 snow:fffafa springgreen:00ff7f steelblue:4682b4 "
        "tan:d2b48c teal:008080 thistle:d8bfd8 tomato:ff6347 "
        "turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff "
        "whitesmoke:f5f5f5 yellow:ffff00 yellowgreen:9acd32"
    ).split()
)


def color(value: str | None) -> str | None:
    """A colour as lower-case ``#rrggbb``, from an SVG colour name or a hex
    code (``#rgb``, ``#rrggbb`` or Qt's ``#aarrggbb``, whose alpha is dropped;
    ``#`` optional). None and ``""``, TiLiA's "no colour", give None; anything
    else comes back stripped and in lower case."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in _CSS:
        return "#" + _CSS[s]
    m = re.fullmatch(r"#?(?:[0-9a-f]{2})?([0-9a-f]{6})", s)
    if m:
        return "#" + m.group(1)
    m = re.fullmatch(r"#?([0-9a-f])([0-9a-f])([0-9a-f])", s)
    if m:
        return "#" + "".join(c * 2 for c in m.groups())
    return s


def field_name(name: str) -> str:
    """``name`` in lower case, with runs of whitespace as ``_``."""
    return re.sub(r"\s+", "_", name.strip().lower())
