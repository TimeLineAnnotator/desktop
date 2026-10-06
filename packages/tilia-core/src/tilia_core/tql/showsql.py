"""What ``Result.sql`` shows: the statements a run executed, in order, each with
its values written in and a ``--`` comment naming the part of the query it
answers, and a comment at each point where Python takes over.

:class:`Recorder` runs the engine's statements and keeps those that answer a
part of the query, as :class:`SqlBlock` s; the reads that only look up names,
titles and positions are run but not shown. :func:`describe_units` names the
parts of a query.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from . import syntax

ORDERS = {
    "STARTS_WITH": "STARTS WITH",
    "ENDS_WITH": "ENDS WITH",
    "CONSISTS_OF": "CONSISTS OF",
}
_WHERE = re.compile("WHERE", re.IGNORECASE)


def sql_literal(value: Any) -> str:
    """``value`` written as an SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def inline(sql: str, params: tuple[Any, ...] | list[Any]) -> str:
    """``sql`` with each ``?`` replaced by the literal of its parameter."""
    parts = sql.split("?")
    return parts[0] + "".join(
        sql_literal(p) + rest for p, rest in zip(params, parts[1:], strict=True)
    )


def one_line(text: str) -> str:
    """``text`` with its white space made single spaces."""
    return " ".join(text.split())


@dataclass(frozen=True)
class SqlBlock:
    """One block of ``Result.sql``: ``comment`` names the part of the query it
    answers (one line, shown after ``--``), and ``statement`` is the statement
    as it ran, its values written in and ending with ``;``, or None where Python
    takes over."""

    comment: str
    statement: str | None = None

    @property
    def text(self) -> str:
        """The block as ``Result.sql`` shows it."""
        if self.statement is None:
            return f"-- {self.comment}"
        return f"-- {self.comment}\n{self.statement}"


def render(blocks: Iterable[SqlBlock]) -> str:
    """``Result.sql``: the blocks one after another, a blank line between two."""
    return "\n\n".join(b.text for b in blocks)


class Recorder:
    """Executes statements on a connection. A statement given a ``part`` is
    remembered as a :class:`SqlBlock`, as shown to the user."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self.blocks: list[SqlBlock] = []
        self._noted: set[str] = set()

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | list[Any] = (),
        part: str | None = None,
    ) -> list[Any]:
        rows = self.con.execute(sql, params).fetchall()
        if part is not None:
            text = inline(sql, params).strip().rstrip(";") + ";"
            self.blocks.append(SqlBlock(one_line(part), text))
        return rows

    def note(self, text: str) -> None:
        """A comment at the point where Python takes over, the first time only
        (the same stage runs again on every file)."""
        text = one_line(text)
        if text not in self._noted:
            self._noted.add(text)
            self.blocks.append(SqlBlock(text))

    @property
    def text(self) -> str:
        return render(self.blocks)


# --------------------------------------------------------------------------- #
# Naming the parts of a query
# --------------------------------------------------------------------------- #
def _skip_quoted(text: str, i: int) -> int:
    """The index after the quoted string or regular expression at ``i``."""
    quote = text[i]
    i += 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _bracket_end(text: str, i: int) -> int:
    """The index after the ``[ … ]`` that opens at ``i``."""
    depth = 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            i = _skip_quoted(text, i)
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def lane_text(lane: syntax.Lane | None) -> str:
    if lane is None:
        return ""
    return f' IN "{lane.text}"' if lane.quoted else f" IN {lane.text}"


def unit_text(text: str, unit: syntax.Unit) -> str:
    """The unit as written: its term, then its brackets."""
    head = ""
    end = unit.pos
    if unit.term is not None:
        head = " OR ".join(a.raw for a in unit.term.alts)
        if unit.term.negate:
            head = "NOT " + head
        last = unit.term.alts[-1]
        end = last.pos + len(last.raw)
    start = end
    while end < len(text) and text[end : end + 1] == "[":
        end = _bracket_end(text, end)
    return head + one_line(text[start:end]) if end > start else head


def step_text(text: str, step: syntax.Step) -> str:
    item = step.item
    if isinstance(item, syntax.Group):
        return "(" + ") OR (".join(seq_text(text, o) for o in item.options) + ")"
    return unit_text(text, item)


def seq_text(text: str, seq: syntax.Seq) -> str:
    return " THEN ".join(step_text(text, s) for s in seq.steps)


def pattern_text(query: syntax.Query) -> str:
    """The pattern of ``query`` as written, without ``WHERE`` or an action."""
    pattern = query.pattern
    if pattern is None:
        return ""
    start = (
        pattern.seq.pos if isinstance(pattern, syntax.SeqPattern) else pattern.left.pos
    )
    end = len(query.text)
    if query.action is not None:
        end = min(end, query.action.pos)
    if query.where:
        first = min(c.pos for c in query.where)
        at = _where_at(query.text, start, first)
        if at >= 0:
            end = min(end, at)
    return one_line(query.text[start:end])


def _where_at(text: str, start: int, end: int) -> int:
    """Where the last ``WHERE`` in ``text[start:end]`` begins, in any case, or
    -1. Not looked for in ``text.upper()``, which can be longer than ``text``
    (``ß`` becomes ``SS``)."""
    found = [m.start() for m in _WHERE.finditer(text, start, end)]
    return found[-1] if found else -1


def where_text(query: syntax.Query) -> str:
    """``WHERE …`` as written, or an empty string."""
    if not query.where:
        return ""
    first = min(c.pos for c in query.where)
    at = _where_at(query.text, 0, first)
    if at < 0:
        return ""
    end = len(query.text) if query.action is None else query.action.pos
    return one_line(query.text[at:end])


def describe_units(query: syntax.Query) -> dict[int, str]:
    """For each unit of the pattern of ``query`` (by ``id``), what its statement
    answers: ``$1: PAC IN cadences``. A unit of a relation's target, with its
    own lane, names that one."""
    out: dict[int, str] = {}
    pattern = query.pattern
    text = query.text

    def seq(
        seq_: syntax.Seq, lane: syntax.Lane | None, first: int, owner: int | None
    ) -> None:
        for n, step in enumerate(seq_.steps, first):
            for unit in _step_units(step):
                what = f"{unit_text(text, unit)}{lane_text(lane)}"
                if owner is None:
                    out[id(unit)] = f"${n}: {what}"
                else:
                    out[id(unit)] = f"in the brackets of ${owner}: {what}"
                for cond in unit.conds:
                    if isinstance(cond, syntax.RelCond):
                        rel = cond.relation
                        seq(rel.target, rel.lane or lane, 1, owner or n)
                    elif isinstance(cond, syntax.Children):
                        seq(cond.seq, lane, 1, owner or n)

    if isinstance(pattern, syntax.SeqPattern):
        seq(pattern.seq, pattern.lane, 1, None)
    elif isinstance(pattern, syntax.RelPattern):
        seq(syntax.Seq([syntax.Step(pattern.left)]), pattern.lane, 1, None)
        seq(pattern.relation.target, pattern.relation.lane or pattern.lane, 2, None)
    return out


def _step_units(step: syntax.Step) -> list[syntax.Unit]:
    if isinstance(step.item, syntax.Group):
        return [u for o in step.item.options for s in o.steps for u in _step_units(s)]
    return [step.item]


def relation_part(query: syntax.Query) -> str:
    """What the join of a sentence-form relation answers: ``$1 SAME END $2``,
    then the relation as written."""
    pattern = query.pattern
    assert isinstance(pattern, syntax.RelPattern)
    rel = pattern.relation
    words = ("NOT " if rel.negate else "") + rel.rel.replace("_", " ")
    return f"$1 {words} $2: {pattern_text(query)}"


def python_stage(query: syntax.Query) -> str:
    """What Python matches after the statements, for the pattern of ``query``."""
    pattern = query.pattern
    text = pattern_text(query)
    if isinstance(pattern, syntax.RelPattern):
        rel = pattern.relation.rel.replace("_", " ")
        return f"{text}: the units above; {rel} is matched in Python, on the lanes."
    assert isinstance(pattern, syntax.SeqPattern)
    what: list[str] = []
    if len(pattern.seq.steps) > 1:
        what.append("THEN")
    if any(s.lo != 1 or s.hi != 1 for s in pattern.seq.steps):
        what.append("the repeats")
    if any(isinstance(s.item, syntax.Group) for s in pattern.seq.steps):
        what.append("the groups")
    if pattern.order:
        what.append(ORDERS[pattern.order])
    if what:
        done = " and ".join(what) + " is matched in Python."
        done = done.replace("is matched", "are matched") if len(what) > 1 else done
        return f"{text}: the units above, in time order per lane; {done}"
    return f"{text}: the units above, in time order per lane."
