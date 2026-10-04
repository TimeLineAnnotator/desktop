"""Label grammars for TQL's tests."""

import re

from tilia_core.labels import fold

_QUALIFIER = re.compile(r"\[[^\]]*\]")
_TRAILING_NUMBER = re.compile(r"\s+\d+$")


class DeClercq:
    """The de Clercq label grammar: parts split on ``/``; in each part,
    whitespace collapsed, a trailing number, ``[qualifiers]`` and trailing
    ``?`` dropped, ``.`` subtypes kept, and the rest folded."""

    def categories(self, label: str) -> tuple[str, ...]:
        found: list[str] = []
        for part in _QUALIFIER.sub("", label).split("/"):
            part = " ".join(part.split()).rstrip("?").rstrip()
            part = _TRAILING_NUMBER.sub("", part).rstrip("?").rstrip()
            category = fold(part)
            if category and category not in found:
                found.append(category)
        return tuple(found)

    def group(self, category: str) -> str | None:
        return None


GRAMMARS = {"de Clercq": DeClercq()}
