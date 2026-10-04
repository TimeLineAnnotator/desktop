"""A plain-English paraphrase of a parsed TQL query.

:func:`explain` turns a :class:`~tilia_core.tql.syntax.Query` into one sentence,
for showing under the query box. The wording is part of the language: it is
fixed, and the tests compare it word for word.
"""

from __future__ import annotations

from .syntax import (
    SEQ_RELATIONS,
    Children,
    Compare,
    Cond,
    Downbeat,
    FieldRef,
    Group,
    Lane,
    Literal,
    Query,
    Relation,
    RelCond,
    RelPattern,
    Seq,
    SeqPattern,
    Step,
    Term,
    Unit,
    Value,
)

__all__ = ["explain"]

_REL_EN = {
    "DURING": "lies inside",
    "CONTAINS": "contains",
    "STARTS_WITH": "starts with",
    "ENDS_WITH": "ends with",
    "CONSISTS_OF": "consists of",
    "STARTS": "is the first thing in",
    "ENDS": "is the last thing in",
    "SAME_START": "starts at the same moment as",
    "SAME_END": "ends at the same moment as",
    "SAME": "covers the same span as",
    "OVERLAPS": "shares time with",
    "BEFORE": "comes before",
    "AFTER": "comes after",
    "STARTS_BEFORE": "starts before",
    "STARTS_AFTER": "starts after",
}
_REL_EN_NOT = {
    "DURING": "does not lie inside",
    "CONTAINS": "contains no",
    "STARTS_WITH": "does not start with",
    "ENDS_WITH": "does not end with",
    "CONSISTS_OF": "does not consist of",
    "STARTS": "is not the first thing in",
    "ENDS": "is not the last thing in",
    "SAME_START": "does not start at the same moment as",
    "SAME_END": "does not end at the same moment as",
    "SAME": "does not cover the same span as",
    "OVERLAPS": "shares no time with",
    "BEFORE": "does not come before",
    "AFTER": "does not come after",
    "STARTS_BEFORE": "does not start before",
    "STARTS_AFTER": "does not start after",
}
_OP_EN = {
    "=": "is",
    "!=": "is not",
    "<": "is below",
    ">": "is above",
    "<=": "is at most",
    ">=": "is at least",
    "~": "matches",
}
_DIRECTLY = ", directly followed by "


def _ex_lit(lit: Literal) -> str:
    if lit.kind == "any":
        return "anything"
    if lit.kind == "exact":
        return f'exactly "{lit.text}"'
    if lit.kind == "regex":
        return f"/{lit.text}/"
    return lit.raw


def _ex_term(t: Term | None) -> str:
    if t is None:
        return "any unit"
    lits = [lit for a in t.alts for lit in a.lits]
    if len(t.alts) == 1 and len(lits) == 1:
        lit = lits[0]
        if lit.kind == "any":
            return "nothing (NOT * excludes every unit)" if t.negate else "any unit"
        if lit.kind == "regex":
            return (
                f"a unit whose label does not match /{lit.text}/"
                if t.negate
                else f"a unit whose label matches /{lit.text}/"
            )
    alts = []
    for a in t.alts:
        if len(a.lits) == 1:
            alts.append(_ex_lit(a.lits[0]))
        else:
            alts.append(" and ".join(_ex_lit(lit) for lit in a.lits) + " together")
    body = " or ".join(alts)
    return f"a unit not labelled {body}" if t.negate else f"a unit labelled {body}"


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _ex_amount(x: float, unit: str | None) -> str:
    """``8 bars``, ``1 beat``, ``0.5s``, ``50% of the piece``; a bare number
    without a unit."""
    if unit in ("beat", "bar"):
        return f"{_num(x)} {unit}{'' if x == 1 else 's'}"
    if unit == "%":
        return f"{_num(x)}% of the piece"
    return f"{_num(x)}{unit or ''}"


def _ex_field(f: FieldRef) -> str:
    s = f"the {f.name}"
    if f.scope == "tl":
        s = f"the timeline's {f.name}"
    elif f.scope == "file":
        s = f"the file's {f.name}"
    if f.index is not None:
        who = "any unit of the match" if f.index == 0 else f"${f.index}"
        s = f"{s} of {who}"
    return s


def _ex_value(v: Value) -> str:
    if v.kind == "range":
        lo, hi = v.value
        return f"{_num(lo)} and {_ex_amount(hi, v.unit)}"
    if v.unit:
        return _ex_amount(v.value, v.unit)
    if v.kind == "ref":
        s = _ex_field(v.value)
        if v.offset:
            amount, unit = v.offset
            s += (
                f" {'plus' if amount >= 0 else 'minus'} "
                f"{_ex_amount(abs(amount), unit)}"
            )
        return s
    if v.kind == "regex":
        return f"/{v.value}/"
    if v.kind == "string":
        return f'"{v.value}"'
    return v.raw


def _ex_cond(c: Cond) -> str:
    if isinstance(c, Compare):
        op = _OP_EN[c.op]
        if c.value.kind == "range":
            op = "is between" if c.op == "=" else "is not between"
        if (
            c.field.name == "parent"
            and c.field.scope is None
            and c.value.kind != "regex"
        ):
            s = (
                f"its parent is {'not ' if c.op == '!=' else ''}"
                f"labelled {_ex_value(c.value)}"
            )
        elif (
            c.field.name == "label"
            and c.field.scope is None
            and c.value.kind == "word"
            and c.op in ("=", "!=")
        ):
            # read as the step would be: a word matches like a step's label
            i, no = c.field.index, c.op == "!="
            who = (
                "it"
                if i is None
                else ("no unit of the match" if no else "a unit of the match")
                if i == 0
                else f"${i}"
            )
            s = f"{who} is {'not ' if no and i != 0 else ''}labelled {c.value.raw}"
        else:
            s = f"{_ex_field(c.field)} {op} {_ex_value(c.value)}"
        return f"not ({s})" if c.negate else s
    if isinstance(c, Downbeat):
        return (
            "it does not start on a downbeat" if c.negate else "it starts on a downbeat"
        )
    if isinstance(c, Children):
        s = _ex_seq(c.seq, plural_hint=True)
        return (
            f"none of its children form {s}"
            if c.negate
            else f"its children include {s}"
        )
    if isinstance(c, RelCond):
        return "it " + _ex_rel(c.relation)
    return "?"


def _ex_rel(r: Relation) -> str:
    words = (_REL_EN_NOT if r.negate else _REL_EN)[r.rel]
    target = _ex_seq(r.target)
    if r.negate and r.rel == "CONTAINS" and target.startswith("a unit "):
        target = target[2:]  # "contains no unit labelled …"
    s = f"{words} {target}"
    s += (
        f" in {_ex_lane(r.lane)}"
        if r.lane
        else (" in its own hierarchy" if r.rel in SEQ_RELATIONS else "")
    )
    if r.within:
        s += f", within {_ex_amount(r.within.amount, r.within.unit)}"
    return s


def _ex_lane(lane: Lane | None) -> str:
    if lane is None:
        return "any timeline"
    return f'"{lane.text}"' if lane.quoted else lane.text


def _ex_quant(lo: int, hi: int | None) -> str:
    if (lo, hi) == (1, 1):
        return ""
    if (lo, hi) == (1, None):
        return "one or more of "
    if (lo, hi) == (0, 1):
        return "optionally "
    if (lo, hi) == (0, None):
        return "any number of "
    if hi is None:
        return f"{lo} or more of "
    if lo == hi:
        return f"exactly {lo} of "
    return f"{lo} to {hi} of "


def _ex_unit(u: Unit) -> str:
    s = _ex_term(u.term)
    if u.conds:
        s += " where " + " and ".join(_ex_cond(c) for c in u.conds)
    return s


def _ex_step(st: Step, joiner: str = _DIRECTLY) -> str:
    it = st.item
    if isinstance(it, Group):
        inner = " or ".join(f"({_ex_seq(o, joiner=joiner)})" for o in it.options)
        body = f"the group {inner}"
    else:
        body = _ex_unit(it)
    return _ex_quant(st.lo, st.hi) + body + (" (the result)" if st.target else "")


def _ex_seq(s: Seq, plural_hint: bool = False, joiner: str = _DIRECTLY) -> str:
    return joiner.join(_ex_step(st, joiner) for st in s.steps)


def explain(q: Query) -> str:
    """A plain-English paraphrase of ``q``, as one sentence ending in a period."""
    parts: list[str] = []
    p = q.pattern
    if isinstance(p, SeqPattern):
        lane = _ex_lane(p.lane) if p.lane else "any timeline with labels"
        if p.within:
            body = (
                _ex_seq(p.seq, joiner=", followed by ")
                + ", where consecutive units may be up to "
                + f"{_ex_amount(p.within.amount, p.within.unit)} apart"
            )
        else:
            body = _ex_seq(p.seq)
        if p.order == "STARTS_WITH":
            parts.append(f"lanes of {lane} that start with {body}")
        elif p.order == "ENDS_WITH":
            parts.append(f"lanes of {lane} that end with {body}")
        elif p.order == "CONSISTS_OF":
            parts.append(f"lanes of {lane} made of exactly {body}")
        else:
            parts.append(f"in {lane}: {body}")
    elif isinstance(p, RelPattern):
        lane = f" in {_ex_lane(p.lane)}" if p.lane else ""
        parts.append(f"{_ex_unit(p.left)}{lane} that {_ex_rel(p.relation)}")
    if q.where:
        parts.append(
            ("where " if parts else "everything where ")
            + " and ".join(_ex_cond(c) for c in q.where)
        )
    if q.action:
        a = q.action
        if a.verb == "DELETE":
            parts.append(
                "then delete each matched unit (or only the category "
                "that matched, when its label has others)"
            )
        elif a.verb == "SET":
            parts.append(
                "then set "
                + ", ".join(
                    f"{_ex_field(x.field)} to {_ex_value(x.value)}" for x in a.assigns
                )
            )
        else:
            parts.append(f"then {a.text}")
    s = "; ".join(parts)
    return s[:1].upper() + s[1:] + "."
