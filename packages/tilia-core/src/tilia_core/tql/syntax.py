"""The TQL parser: query text in, one syntax tree out, or a :class:`TQLError`.

This module is TQL 0.1.0's lexer, syntax tree and parser. It is **corpus-free**
(matching against timelines lives elsewhere), so the grammar can be tested
without loading a file. The grammar, as implemented (``:=`` is "is", ``|``
"or", ``[…]`` "optional", ``(…)*`` "repeated")::

    query     := pattern [where] [action]
               | where [action]                     -- fields only
    pattern   := [order] seq [IN lane] [within]     -- a run inside one lane
               | unit [IN lane] relation            -- the left unit is the target
    order     := STARTS WITH | ENDS WITH | CONSISTS OF   -- the whole lane
    seq       := step (THEN step)*
    step      := ['@'] item [quant]                 -- '@': this step is the target
    item      := term [brackets] | brackets         -- one component
               | '(' seq ')' (OR '(' seq ')')*      -- a group
    brackets  := '[' conds ']'
    term      := [NOT] alt (OR alt)*
    alt       := literal ('/' literal)*             -- AND within one component
    literal   := word ['.' subtype] | "exact label" | /regex/ | '*'
    quant     := '+' | '?' | '*' | '{' m [',' [n]] '}'
    lane      := role | "timeline name" | kind | word
    relation  := [NOT] rel target [IN lane] [within]
    rel       := DURING | CONTAINS | STARTS [WITH] | ENDS [WITH] | CONSISTS OF
               | SAME [START | END] | OVERLAPS | BEFORE | AFTER
               | STARTS (BEFORE | AFTER)            -- starts only
    within    := WITHIN amount unit                 -- after a sequence: the largest
                                                    --   gap a THEN crosses
    where     := WHERE conds
    conds     := cond (AND cond)*
    cond      := [NOT] field op value | downbeat | [NOT] seq | [NOT] relation
    field     := [$n.] [file. | tl.] name
    op        := = | != | ~ | < | > | <= | >=       -- ranges: a..b
    value     := number | time | "text" | word | /regex/ | a..b | $n.field
               | $n.time (+ | -) amount [unit]       -- a distance: $2.start + 16 bars
    action    := '->' SET field = value (',' field = value)*
               | '->' DELETE
               | '->' (TAG | UNTAG) [$n] "tag"       -- $n: that step's units; $0: all
               | '->' UNTAG [$n] '*'
               | '->' GROUP AS "label" [COLOR "#rrggbb"] [on]
               | '->' UNGROUP
    on        := ON (shape '->' resolution)+
    shape     := free | congruent | enclosing | crossing
    resolution := INSERT | ADD-CATEGORY | SKIP [TAG "tag"]

Lexical rules:

* Keywords are case-insensitive and **reserved**: ``THEN OR NOT AND IN WHERE
  WITHIN DURING CONTAINS STARTS ENDS CONSISTS SAME OVERLAPS BEFORE AFTER``. A
  label spelled like one has to be quoted. ``WITH``, ``OF``, ``START`` and
  ``END`` are keywords only right after the word that needs them, so a step
  called ``end`` still reads as a label.
* A *word* runs until whitespace or one of ``[ ] ( ) { } " , = < > ! ~ / $ @``.
  ``: . ' - | # _ ? *`` stay inside words (``a:``, ``A'.compound``, ``b'|seq``,
  ``_?verse``, ``#ffc0cb``). One trailing ``+ ? *`` is a quantifier. ``@``
  marks the target of a sequence.
* ``/`` starts a regular expression where a literal or a value is expected
  (after ``[``, ``(``, an operator or a keyword) and means "and" between two
  literals otherwise, so ``verse/chorus`` and ``NOT /^_/`` both read as meant.
* ``"…"`` is a string (``\\"`` and ``\\\\`` escape); ``-- …`` to the end of a
  line is a comment.
* Text in any script: words, strings and regular expressions are read in one
  Unicode normal form (NFC), and keywords are ASCII. Error offsets count the
  characters as typed.
* Forms the prototype accepts and TQL 0.1.0 leaves out (``$n.first``,
  ``$n.last``, ``$-1``, ``1:30:00``, a value in milliseconds, a percentage with
  ``duration``) raise a :class:`TQLError` saying so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Union

from tilia_core.labels import nfc

__all__ = ["TQLError", "parse", "format_error", "KEYWORDS", "Query"]


class TQLError(ValueError):
    """A malformed query. ``pos``/``end`` are character offsets into the text,
    so a caller can underline the culprit (see :func:`format_error`)."""

    def __init__(
        self, msg: str, pos: int | None = None, end: int | None = None
    ) -> None:
        super().__init__(msg)
        self.msg = msg
        self.pos = pos
        self.end = end if end is not None else (pos + 1 if pos is not None else None)


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
KEYWORDS = frozenset(
    {
        "THEN",
        "OR",
        "NOT",
        "AND",
        "IN",
        "WHERE",
        "WITHIN",
        "DURING",
        "CONTAINS",
        "STARTS",
        "ENDS",
        "CONSISTS",
        "SAME",
        "OVERLAPS",
        "BEFORE",
        "AFTER",
    }
)
RELATION_HEADS = frozenset(
    {
        "DURING",
        "CONTAINS",
        "STARTS",
        "ENDS",
        "CONSISTS",
        "SAME",
        "OVERLAPS",
        "BEFORE",
        "AFTER",
    }
)
VERBS = ("SET", "GROUP", "UNGROUP", "TAG", "UNTAG", "DELETE")
_SHAPES = ("free", "congruent", "enclosing", "crossing")
_RESOLUTIONS = ("INSERT", "ADD-CATEGORY", "SKIP")
# Relations whose target may be a whole sequence ("B may be a sequence").
SEQ_RELATIONS = frozenset({"CONTAINS", "STARTS_WITH", "ENDS_WITH", "CONSISTS_OF"})

_STOP = set('[](){}",=<>!~/$@')
_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_GROUP_RE = re.compile(
    r'^AS\s+(?P<label>"(?:[^"\\]|\\.)*")(?:\s+COLOR\s+(?P<color>"(?:[^"\\]|\\.)*"))?$',
    re.I,
)
_COUNT_RE = re.compile(r"\{\s*(\d+)\s*(?:(,)\s*(\d*)\s*)?\}")
_REF_RE = re.compile(r"\$(-?\d+)((?:\.[A-Za-z_][A-Za-z_0-9]*)*)")
_NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")
_NUM_UNIT_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+))([A-Za-z]+)$")
_TIME_RE = re.compile(r"^(\d+):(\d{1,2}(?:\.\d+)?)$")
_PERCENT_RE = re.compile(r"^(\d+\.?\d*|\.\d+)%$")  # of the piece's length
_UNITS = {
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "ms": "ms",
    "beat": "beat",
    "beats": "beat",
    "bar": "bar",
    "bars": "bar",
    "measure": "bar",
    "measures": "bar",
}
_BAR_NUMBERS = ("bar", "end_bar", "bar.count", "bar.label", "pass")


@dataclass
class Tok:
    type: str  # WORD STRING REGEX REF QUANT OP ARROW SLASH AT [ ] ( ) , EOF
    text: str  # the source text of the token
    pos: int
    end: int
    value: Any = None

    @property
    def upper(self) -> str:
        """The word in capitals, for telling keywords; only an ASCII word can be
        one, since ``"ın".upper()`` is ``IN`` and ``"ſame".upper()`` ``SAME``."""
        return self.text.upper() if self.type == "WORD" and self.text.isascii() else ""


def _not_in_v01(form: str, pos: int, end: int) -> TQLError:
    """The error for a form the prototype reads and TQL 0.1.0 leaves out."""
    return TQLError(f"{form} is not part of TQL v0.1.0", pos, end)


def _opens_operand(toks: list[Tok]) -> bool:
    """Whether a ``/`` after the tokens so far starts a regex (a literal or a
    value is expected there) rather than joining two literals."""
    prev = toks[-1] if toks else None
    if prev is None:
        return True
    if prev.type in ("[", "(", ",", "OP", "ARROW", "AT"):
        return True
    if prev.type != "WORD":
        return False
    if prev.upper in (KEYWORDS | {"WITH", "OF"}):
        return True
    # START / END are keywords only right after SAME: `SAME START /^v/`
    return (
        prev.upper in ("START", "END")
        and len(toks) > 1
        and toks[-2].type == "WORD"
        and toks[-2].upper == "SAME"
    )


def lex(text: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(text)

    def add(t: Tok) -> None:
        toks.append(t)

    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        # `-- comment` to the end of the line (only at a token boundary, so a
        # label such as `a--b` keeps its dashes)
        if text.startswith("--", i) and (i == 0 or text[i - 1].isspace()):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n and text[j + 1] in '"\\':
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            if j >= n:
                raise TQLError('unterminated string - a closing " is missing', i, n)
            add(Tok("STRING", text[i : j + 1], i, j + 1, nfc("".join(buf))))
            i = j + 1
            continue
        if ch in "[](),":
            add(Tok(ch, ch, i, i + 1))
            i += 1
            continue
        if ch == "@":  # the target of a sequence
            add(Tok("AT", ch, i, i + 1))
            i += 1
            continue
        if ch == "{":
            m = _COUNT_RE.match(text, i)
            if not m:
                raise TQLError(
                    "'{' starts a count such as {2} or {2,4}; a label "
                    "with braces must be quoted",
                    i,
                )
            lo = int(m.group(1))
            hi = lo if not m.group(2) else (int(m.group(3)) if m.group(3) else None)
            add(Tok("QUANT", m.group(0), i, m.end(), (lo, hi)))
            i = m.end()
            continue
        if text.startswith("->", i):
            add(Tok("ARROW", "->", i, i + 2))
            i += 2
            continue
        two = text[i : i + 2]
        if two in ("!=", "<=", ">="):
            add(Tok("OP", two, i, i + 2))
            i += 2
            continue
        if ch in "=<>~":
            add(Tok("OP", ch, i, i + 1))
            i += 1
            continue
        if ch == "!":
            raise TQLError(
                "'!' only appears in '!='; a label with '!' must be quoted", i
            )
        if ch == "}":
            raise TQLError("unmatched '}'", i)
        if ch == "/":
            if _opens_operand(toks):
                j, buf = i + 1, []
                while j < n and text[j] != "/":
                    if text[j] == "\\" and j + 1 < n and text[j + 1] == "/":
                        buf.append("/")
                        j += 2
                        continue
                    buf.append(text[j])
                    j += 1
                if j >= n:
                    raise TQLError(
                        "unterminated /regex/ - the closing / is missing", i, n
                    )
                pat = nfc("".join(buf))
                try:
                    re.compile(pat)
                except re.error as exc:
                    raise TQLError(
                        f"bad regular expression /{pat}/: {exc}", i, j + 1
                    ) from None
                add(Tok("REGEX", text[i : j + 1], i, j + 1, pat))
                i = j + 1
            else:
                add(Tok("SLASH", "/", i, i + 1))
                i += 1
            continue
        if ch == "$":
            m = _REF_RE.match(text, i)
            if not m:
                raise TQLError(
                    "'$' must be followed by a number, as in $1 or $2.label", i
                )
            path = [p for p in m.group(2).split(".") if p]
            if m.group(1).startswith("-"):
                raise _not_in_v01(f"${m.group(1)}", i, i + 1 + len(m.group(1)))
            if path and path[0].lower() in ("first", "last"):
                end = i + 1 + len(m.group(1)) + 1 + len(path[0])
                raise _not_in_v01(text[i:end], i, end)
            add(Tok("REF", m.group(0), i, m.end(), (int(m.group(1)), path)))
            i = m.end()
            continue
        # a word: up to whitespace, a stop character or an arrow
        j = i
        while (
            j < n
            and not text[j].isspace()
            and text[j] not in _STOP
            and not text.startswith("->", j)
        ):
            j += 1
        word = text[i:j]
        # peel ONE trailing quantifier; `*` alone is the wildcard literal —
        # except right after `)`, `]` or a quoted literal, where no new step can
        # start, so `(verse THEN chorus)*` repeats the group
        k = len(word)
        while k > 0 and word[k - 1] in "+?*":
            k -= 1
        body, quants = word[:k], word[k:]
        after_item = bool(toks) and toks[-1].type in (")", "]", "STRING", "REGEX")
        if not body and quants.startswith("*") and not after_item:  # `*`, `*+`, `**`
            body, quants = "*", quants[1:]
        if len(quants) > 1:
            raise TQLError(
                f"{word!r} has more than one quantifier - one of + ? * "
                "goes at the end of a step",
                i,
                j,
            )
        if body:
            add(Tok("WORD", nfc(body), i, i + len(body)))  # offsets stay the typed ones
        if quants:
            q = quants
            lo, hi = {"+": (1, None), "?": (0, 1), "*": (0, None)}[q]
            add(Tok("QUANT", q, j - 1, j, (lo, hi)))
        i = j
    toks.append(Tok("EOF", "", n, n))
    return toks


# --------------------------------------------------------------------------- #
# Syntax tree
# --------------------------------------------------------------------------- #
@dataclass
class Literal:
    kind: str  # "word" | "exact" | "regex" | "any"
    text: str  # word head / exact label / regex pattern
    sub: str | None = None  # word subtype: bridge.modern -> sub "modern"
    raw: str = ""  # as written
    pos: int = 0


@dataclass
class Alt:  # literals joined by '/': all on one component
    lits: list[Literal]
    raw: str = ""
    pos: int = 0


@dataclass
class Term:  # [NOT] alt (OR alt)*
    alts: list[Alt]
    negate: bool = False
    pos: int = 0


@dataclass
class Unit:  # one component: a term and/or bracket conditions
    term: Term | None
    conds: list[Cond] = field(default_factory=list)
    pos: int = 0


@dataclass
class Group:  # ( seq ) (OR ( seq ))*
    options: list[Seq]
    pos: int = 0


@dataclass
class Step:
    item: Unit | Group
    lo: int = 1
    hi: int | None = 1
    pos: int = 0
    target: bool = False  # marked with @: what the query is about


@dataclass
class Seq:
    steps: list[Step]
    pos: int = 0


@dataclass
class Lane:
    text: str
    quoted: bool
    pos: int = 0


@dataclass
class Within:
    amount: float
    unit: str  # s | ms | beat | bar
    pos: int = 0


@dataclass
class Relation:
    rel: str  # DURING CONTAINS STARTS_WITH ENDS_WITH CONSISTS_OF
    # STARTS ENDS SAME_START SAME_END SAME OVERLAPS
    # BEFORE AFTER STARTS_BEFORE STARTS_AFTER
    target: Seq
    lane: Lane | None = None
    within: Within | None = None
    negate: bool = False
    pos: int = 0


@dataclass
class FieldRef:
    name: str  # "label", "bar.count", "composer", …
    scope: str | None = None  # None | "file" | "tl"
    index: int | None = None  # $n
    raw: str = ""
    pos: int = 0


@dataclass
class Value:
    kind: str  # number | string | word | regex | range | ref | any
    value: Any = None  # float | str | (lo, hi) | FieldRef
    raw: str = ""
    pos: int = 0
    unit: str | None = None  # bar | beat: a length (`duration = 8 bars`); %: of
    # the piece (`start >= 50%`); seconds are converted
    # on parsing and leave no unit
    offset: tuple[float, str] | None = None  # (signed amount, s | % | beat | bar): a
    # distance added to a ref,
    # `$2.start + 16 bars`


@dataclass
class Compare:
    field: FieldRef
    op: str
    value: Value
    negate: bool = False
    pos: int = 0


@dataclass
class Downbeat:
    pos: int = 0
    negate: bool = False


@dataclass
class Children:
    seq: Seq
    negate: bool = False
    pos: int = 0


@dataclass
class RelCond:
    relation: Relation
    pos: int = 0


Cond = Union[Compare, Downbeat, Children, RelCond]


@dataclass
class SeqPattern:
    seq: Seq
    lane: Lane | None = None
    order: str | None = None  # None | STARTS_WITH | ENDS_WITH | CONSISTS_OF
    within: Within | None = None  # THEN … WITHIN: the largest gap a THEN crosses


@dataclass
class RelPattern:
    left: Unit
    lane: Lane | None
    relation: Relation


@dataclass
class Assign:
    field: FieldRef
    value: Value


@dataclass
class OnRule:
    """One ``shape -> resolution`` pair of a GROUP's ``ON`` clause, as written."""

    shape: str  # free | congruent | enclosing | crossing
    resolution: str  # INSERT | ADD-CATEGORY | SKIP
    tag: str | None = None  # SKIP TAG "x"


@dataclass
class Action:
    verb: str  # SET | GROUP | UNGROUP | TAG | UNTAG | DELETE
    assigns: list[Assign] = field(default_factory=list)  # SET
    label: str | None = None  # GROUP AS "label"
    color: str | None = None  # GROUP AS "label" COLOR "#rrggbb"
    on: list[OnRule] = field(default_factory=list)  # GROUP ... ON, as written
    tag: str | None = None  # TAG "x" / UNTAG "x" | UNTAG *
    unit: int | None = None  # TAG $n "x" / UNTAG $n "x": whose units; 0 is all
    text: str = ""
    pos: int = 0


@dataclass
class Query:
    pattern: SeqPattern | RelPattern | None
    where: list[Cond] = field(default_factory=list)
    action: Action | None = None
    text: str = ""

    @property
    def has_target(self) -> bool:
        """Whether a step is marked with ``@``: then only the marked steps are
        the result, and the others context."""
        p = self.pattern
        return isinstance(p, SeqPattern) and any(True for _ in _marked(p.seq))

    @property
    def slot_count(self) -> int:
        """How many numbered units ($1, $2, …) a match of this query has."""
        p = self.pattern
        if isinstance(p, SeqPattern):
            return len(p.seq.steps)
        if isinstance(p, RelPattern):
            # "has no …" matches the left unit alone: there is no right one
            return 1 if p.relation.negate else 1 + len(p.relation.target.steps)
        return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.toks = lex(text)
        self.i = 0
        self.unit_tok: Tok | None = None  # the $n of TAG $n / UNTAG $n

    # -- cursor ------------------------------------------------------------ #
    def peek(self, k: int = 0) -> Tok:
        j = min(self.i + k, len(self.toks) - 1)
        return self.toks[j]

    def next(self) -> Tok:
        t = self.toks[self.i]
        if t.type != "EOF":
            self.i += 1
        return t

    def at(self, typ: str, k: int = 0) -> bool:
        return self.peek(k).type == typ

    def at_kw(self, *names: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.type == "WORD" and t.upper in names

    def expect(self, typ: str, what: str) -> Tok:
        t = self.peek()
        if t.type != typ:
            raise self.err(f"expected {what}, found {self.describe(t)}", t)
        return self.next()

    def expect_kw(self, name: str) -> Tok:
        t = self.peek()
        if not (t.type == "WORD" and t.upper == name):
            raise self.err(f"expected {name}, found {self.describe(t)}", t)
        return self.next()

    @staticmethod
    def describe(t: Tok) -> str:
        if t.type == "EOF":
            return "the end of the query"
        if t.type == "WORD" and t.upper in KEYWORDS:
            return f"keyword {t.upper}"
        return repr(t.text)

    @staticmethod
    def err(msg: str, t: Tok) -> TQLError:
        return TQLError(msg, t.pos, max(t.end, t.pos + 1))

    def at_relation(self, k: int = 0) -> bool:
        """A relation (optionally negated) starts here."""
        if self.at_kw("NOT", k=k):
            k += 1
        return self.at_kw(*RELATION_HEADS, k=k)

    # -- query ------------------------------------------------------------- #
    def query(self) -> Query:
        if self.at("EOF"):
            raise TQLError("empty query", 0)
        pattern = None
        if not self.at_kw("WHERE"):
            pattern = self.pattern()
        where: list[Cond] = []
        if self.at_kw("WHERE"):
            self.next()
            where = self.conds(context="where")
        action = self.action() if self.at("ARROW") else None
        t = self.peek()
        if t.type != "EOF":
            raise self.err(self.trailing_hint(t), t)
        q = Query(pattern, where, action, self.text)
        self.check_refs(q)
        self.check_targets(q)
        return q

    def trailing_hint(self, t: Tok) -> str:
        if t.type == "(":
            return (
                "unexpected '(' - parentheses only group steps, as in "
                "(verse THEN chorus)+. For 'a unit whose children are ...' "
                "write the children in brackets: SRDC[verse THEN chorus]"
            )
        if t.type == "WORD" and t.upper in VERBS:
            return f"{t.upper} is an action - write it after '->'"
        if t.type == "AT":
            return (
                "unexpected '@' - it marks a step and goes right before it, as in "
                "verse THEN @chorus"
            )
        if t.type == "WORD" and t.upper not in KEYWORDS:
            return (
                f"unexpected {t.text!r} - steps are joined by THEN, and a "
                "label with spaces or operator characters must be quoted "
                f'("... {t.text}")'
            )
        return f"unexpected {self.describe(t)}"

    def pattern(self) -> SeqPattern | RelPattern:
        order = None
        t = self.peek()
        if self.at_kw("STARTS") and self.at_kw("WITH", k=1):
            order = "STARTS_WITH"
        elif self.at_kw("ENDS") and self.at_kw("WITH", k=1):
            order = "ENDS_WITH"
        elif self.at_kw("CONSISTS") and self.at_kw("OF", k=1):
            order = "CONSISTS_OF"
        elif self.at_kw(*RELATION_HEADS):
            raise self.err(
                f"a query cannot start with {t.upper} - put the unit it "
                f"relates first, e.g. '* IN cadences {t.upper} ST IN form'"
                + (
                    "; at the start, only STARTS WITH / ENDS WITH / "
                    "CONSISTS OF (the whole lane) are allowed"
                    if t.upper in ("STARTS", "ENDS", "CONSISTS")
                    else ""
                ),
                t,
            )
        if order:
            self.next()
            self.next()
        seq = self.seq()
        lane = self.lane_opt()
        if self.at_relation():
            if order:
                raise self.err(
                    "a query that starts with "
                    + order.replace("_", " ")
                    + " cannot also hold a relation",
                    self.peek(),
                )
            if len(seq.steps) != 1 or not isinstance(seq.steps[0].item, Unit):
                raise TQLError(
                    "the left side of a relation is one unit, not a "
                    "sequence or a group - move the sequence into "
                    "brackets, e.g. ST[CONTAINS HC THEN PAC IN cadences]",
                    seq.pos,
                    self.peek().pos,
                )
            st = seq.steps[0]
            if (st.lo, st.hi) != (1, 1):
                raise TQLError(
                    "the left side of a relation takes no quantifier",
                    st.pos,
                    self.peek().pos,
                )
            if st.target:
                raise TQLError(_REL_NO_AT, st.pos, st.pos + 1)
            rel = self.relation()
            return RelPattern(st.item, lane, rel)
        within = self.within_opt()
        if within is not None:
            if not _joins_units(seq):
                raise TQLError(
                    "WITHIN after a sequence says how far apart its steps may "
                    "be, and this one has a single step - for the distance to "
                    "another unit use a relation, e.g. verse IN form BEFORE "
                    "chorus IN form WITHIN 2 bars",
                    within.pos,
                    self.peek().pos,
                )
            if self.at_kw("IN"):
                raise self.err(
                    "IN goes before WITHIN: verse THEN chorus IN form " "WITHIN 2 bars",
                    self.peek(),
                )
        return SeqPattern(seq, lane, order, within)

    # -- sequences --------------------------------------------------------- #
    def seq(self) -> Seq:
        start = self.peek().pos
        steps = [self.step()]
        while self.at_kw("THEN"):
            self.next()
            steps.append(self.step())
        self.check_anchor_words(steps)
        return Seq(steps, start)

    def check_anchor_words(self, steps: list[Step]) -> None:
        """The START / END anchors of the first prototypes are gone. Written in
        capitals at the edge of a sequence they are almost certainly the old
        anchor, which would now silently search for a label called "start"."""

        def word_of(st: Step) -> str | None:
            it = st.item
            if (
                isinstance(it, Unit)
                and it.term
                and len(it.term.alts) == 1
                and len(it.term.alts[0].lits) == 1
            ):
                lit = it.term.alts[0].lits[0]
                if lit.kind == "word" and lit.sub is None:
                    return lit.raw
            return None

        if len(steps) > 1 and word_of(steps[0]) == "START":
            raise TQLError(
                "START THEN ... is the old anchor - write STARTS WITH ... "
                'IN lane (or quote "START" to match a label)',
                steps[0].pos,
            )
        if len(steps) > 1 and word_of(steps[-1]) == "END":
            raise TQLError(
                "... THEN END is the old anchor - write ENDS WITH ... "
                'IN lane (or quote "END" to match a label)',
                steps[-1].pos,
            )

    def step(self) -> Step:
        t = self.peek()
        target = t.type == "AT"
        if target:
            self.next()
            if self.at("AT"):
                raise self.err("one @ marks a step", self.peek())
            if self.at("EOF") or self.at_kw("THEN", "IN", "WHERE"):
                raise self.err(
                    "@ marks the step after it, as in * THEN @bridge THEN *",
                    self.peek(),
                )
        if self.peek().type == "QUANT":
            raise self.err(
                "a quantifier needs a step before it, as in verse+", self.peek()
            )
        item = self.item()
        lo, hi = 1, 1
        if self.at("QUANT"):
            q = self.next()
            lo, hi = q.value
            if hi is not None and hi < 1:
                raise self.err(
                    f"quantifier {q.text} would match nothing "
                    "(the maximum must be at least 1)",
                    q,
                )
            if hi is not None and lo > hi:
                raise self.err(f"quantifier {q.text} has min > max", q)
            if self.at("QUANT"):
                raise self.err("one quantifier per step", self.peek())
        return Step(item, lo, hi, t.pos, target)

    def item(self) -> Unit | Group:
        t = self.peek()
        if t.type == "(":
            return self.group()
        if t.type == "[":
            return Unit(None, self.brackets(), t.pos)
        if self.at_kw("NOT") and self.at("(", k=1):
            raise self.err(
                "NOT does not apply to groups - for 'has no ...' use NOT "
                "in brackets, e.g. ST[NOT continuation]",
                t,
            )
        term = self.term()
        conds = self.brackets() if self.at("[") else []
        return Unit(term, conds, t.pos)

    def group(self) -> Group:
        start = self.peek().pos
        options = []
        while True:
            self.expect("(", "'('")
            if self.at(")"):
                raise self.err("empty group ()", self.peek())
            options.append(self.seq())
            self.expect(")", "')' to close the group")
            if self.at_kw("OR") and self.at("(", k=1):
                self.next()
                continue
            if self.at_kw("OR"):
                raise self.err(
                    "OR after a group joins another group - write "
                    "(a THEN b) OR (c THEN d)",
                    self.peek(),
                )
            return Group(options, start)

    def term(self) -> Term:
        start = self.peek().pos
        negate = False
        if self.at_kw("NOT"):
            self.next()
            negate = True
        alts = [self.alt()]
        while self.at_kw("OR"):
            self.next()
            if self.at("("):
                raise self.err(
                    "OR between a label and a group is not allowed - "
                    "wrap both sides in ( )",
                    self.peek(),
                )
            alts.append(self.alt())
        return Term(alts, negate, start)

    def alt(self) -> Alt:
        start = self.peek().pos
        lits = [self.literal()]
        while self.at("SLASH"):
            self.next()
            lits.append(self.literal())
        end = self.toks[self.i - 1].end
        return Alt(lits, nfc(self.text[start:end]), start)

    def literal(self) -> Literal:
        t = self.peek()
        if t.type == "STRING":
            self.next()
            return Literal("exact", t.value, None, t.text, t.pos)
        if t.type == "REGEX":
            self.next()
            return Literal("regex", t.value, None, t.text, t.pos)
        if t.type == "WORD":
            if t.upper in KEYWORDS:
                raise self.err(
                    f"expected a label, found keyword {t.upper} - quote "
                    f'it ("{t.text}") to match a label spelled so',
                    t,
                )
            self.next()
            if t.text == "*":
                return Literal("any", "*", None, "*", t.pos)
            head, dot, sub = t.text.partition(".")
            if not head:
                raise self.err(f"missing name before '.' in {t.text!r}", t)
            if dot and not sub:
                raise self.err(f"missing subtype after '.' in {t.text!r}", t)
            return Literal("word", head, sub or None, t.text, t.pos)
        if t.type == "SLASH":
            raise self.err(
                "'/' joins two labels on one unit (verse/chorus); a "
                "regular expression goes where a label starts",
                t,
            )
        raise self.err(f"expected a label, found {self.describe(t)}", t)

    # -- lanes, relations -------------------------------------------------- #
    def lane_opt(self) -> Lane | None:
        if not self.at_kw("IN"):
            return None
        self.next()
        t = self.peek()
        if t.type == "STRING":
            self.next()
            return Lane(t.value, True, t.pos)
        if t.type == "WORD" and t.upper not in KEYWORDS and t.text != "*":
            self.next()
            return Lane(t.text, False, t.pos)
        raise self.err(
            "IN needs a lane: a role (form, cadences...), a kind "
            '(markers, ranges...) or a "timeline name"',
            t,
        )

    def relation(self) -> Relation:
        start = self.peek().pos
        negate = False
        if self.at_kw("NOT"):
            self.next()
            negate = True
        t = self.next()
        head = t.upper
        if head == "DURING":
            rel = "DURING"
        elif head == "CONTAINS":
            rel = "CONTAINS"
        elif head in ("STARTS", "ENDS"):
            if self.at_kw("WITH"):
                self.next()
                rel = head + "_WITH"
            elif head == "STARTS" and self.at_kw("BEFORE", "AFTER"):
                rel = "STARTS_" + self.next().upper  # compares starts only
            elif self.at_kw("BEFORE", "AFTER"):
                raise self.err(
                    f"ENDS {self.peek().upper} is not a relation - STARTS "
                    f"{self.peek().upper} compares starts; to compare ends, "
                    'pair the units and use WHERE, e.g. * IN "Form (A)" '
                    'OVERLAPS * IN "Form (B)" WHERE $1.end < $2.end',
                    self.peek(),
                )
            else:
                rel = head
        elif head == "CONSISTS":
            self.expect_kw("OF")
            rel = "CONSISTS_OF"
        elif head == "SAME":
            if self.at_kw("START"):
                self.next()
                rel = "SAME_START"
            elif self.at_kw("END"):
                self.next()
                rel = "SAME_END"
            else:
                rel = "SAME"
        elif head in ("OVERLAPS", "BEFORE", "AFTER"):
            rel = head
        else:
            raise self.err(f"expected a relation, found {self.describe(t)}", t)
        target = self.seq()
        if rel not in SEQ_RELATIONS:
            if (
                len(target.steps) != 1
                or not isinstance(target.steps[0].item, Unit)
                or (target.steps[0].lo, target.steps[0].hi) != (1, 1)
            ):
                raise TQLError(
                    f"{rel.replace('_', ' ')} relates two units - its "
                    "right side is one unit, not a sequence (only "
                    "CONTAINS, STARTS WITH, ENDS WITH and CONSISTS OF "
                    "take sequences)",
                    target.pos,
                    self.peek().pos,
                )
        lane = self.lane_opt()
        within = self.within_opt()
        return Relation(rel, target, lane, within, negate, start)

    def within_opt(self) -> Within | None:
        if not self.at_kw("WITHIN"):
            return None
        kw = self.next()
        t = self.peek()
        if t.type != "WORD":
            raise self.err(
                "WITHIN needs an amount, e.g. WITHIN 2 bars or WITHIN 0.5 s", t
            )
        self.next()
        m = _NUM_UNIT_RE.match(t.text)
        if m:
            amount, unit = float(m.group(1)), m.group(2).lower()
        elif _NUM_RE.match(t.text):
            amount = float(t.text)
            u = self.peek()
            if u.type != "WORD" or u.text.lower() not in _UNITS:
                raise self.err(
                    "WITHIN needs a unit after the amount: s, ms, beats " "or bars", u
                )
            self.next()
            unit = u.text.lower()
        else:
            raise self.err(f"WITHIN needs a number, found {t.text!r}", t)
        if unit not in _UNITS:
            raise self.err(f"unknown unit {unit!r} - one of s, ms, beats, bars", t)
        if amount < 0:
            raise self.err("WITHIN needs a positive amount", t)
        return Within(amount, _UNITS[unit], kw.pos)

    # -- conditions -------------------------------------------------------- #
    def brackets(self) -> list[Cond]:
        self.expect("[", "'['")
        if self.at("]"):
            raise self.err(
                "empty brackets [] - put a condition inside, or use *", self.peek()
            )
        conds = self.conds(context="bracket")
        self.expect(
            "]", "']' to close the brackets (conditions inside are joined by AND)"
        )
        return conds

    def conds(self, context: str) -> list[Cond]:
        out = [self.cond(context)]
        while self.at_kw("AND"):
            self.next()
            out.append(self.cond(context))
        if self.at_kw("OR"):
            raise self.err(
                "conditions are joined by AND; OR only joins labels "
                "(a OR b) or groups",
                self.peek(),
            )
        return out

    def looks_like_compare(self, k: int = 0) -> bool:
        t = self.peek(k)
        if t.type == "REF":
            return True
        return (
            t.type == "WORD"
            and t.upper not in KEYWORDS
            and self.peek(k + 1).type == "OP"
        )

    def at_downbeat(self, k: int = 0) -> bool:
        """``downbeat`` standing alone as a condition (not a children step)."""
        t = self.peek(k)
        return (
            t.type == "WORD"
            and t.text.lower() == "downbeat"
            and (
                self.at("]", k=k + 1)
                or self.at_kw("AND", k=k + 1)
                or self.at("EOF", k=k + 1)
                or self.at("ARROW", k=k + 1)
            )
        )

    def cond(self, context: str) -> Cond:
        t = self.peek()
        if self.at_kw("NOT"):
            if self.at_kw(*RELATION_HEADS, k=1):
                return RelCond(self.relation(), t.pos)
            if self.looks_like_compare(1):
                self.next()
                c = self.compare()
                c.negate = True
                c.pos = t.pos
                return c
            if self.at_downbeat(1):
                self.next()
                self.next()
                return Downbeat(t.pos, True)
            self.next()
            return Children(self.seq(), True, t.pos)
        if self.at_kw(*RELATION_HEADS):
            return RelCond(self.relation(), t.pos)
        if self.looks_like_compare():
            return self.compare()
        if self.at_downbeat():
            self.next()
            return Downbeat(t.pos)
        if t.type in ("EOF", "]", "ARROW"):
            raise self.err(f"expected a condition, found {self.describe(t)}", t)
        seq = self.seq()
        if self.at_kw("IN"):
            raise self.err(
                "children are always in the unit's own hierarchy - "
                "for another timeline use a relation, e.g. "
                "[CONTAINS PAC IN cadences]",
                self.peek(),
            )
        return Children(seq, False, t.pos)

    def field_ref(self) -> FieldRef:
        t = self.next()
        if t.type == "REF":
            index, path = t.value
            scope = None
            if path and path[0].lower() in ("file", "tl"):
                scope = path[0].lower()
                path = path[1:]
            if not path:
                raise self.err(f"{t.text} needs a field, as in {t.text}.label", t)
            return FieldRef(".".join(path).lower(), scope, index, t.text, t.pos)
        if t.type != "WORD":
            raise self.err(f"expected a field name, found {self.describe(t)}", t)
        parts = t.text.split(".")
        scope = None
        if len(parts) > 1 and parts[0].lower() in ("file", "tl"):
            scope = parts[0].lower()
            parts = parts[1:]
        name = ".".join(parts)
        if not name or not re.match(r"^[A-Za-z_][A-Za-z_0-9.]*$", name):
            raise self.err(f"{t.text!r} is not a field name", t)
        return FieldRef(name.lower(), scope, None, t.text, t.pos)

    def compare(self) -> Compare:
        start = self.peek().pos
        f = self.field_ref()
        op_t = self.expect("OP", "an operator (= != ~ < > <= >=)")
        v = self.unit_opt(self.value())
        if v.kind == "ref":
            v = self.distance_opt(f, op_t, v)
        if v.unit == "%" and not f.scope and f.name == "duration":
            end = v.pos + len(v.raw)
            raise _not_in_v01(self.text[f.pos : end], f.pos, end)
        if v.unit == "%" and (f.scope or f.name not in ("start", "end", "time")):
            raise TQLError(
                f"a percentage of the piece compares with a time - start, end "
                f"or time, not {f.raw}",
                v.pos,
                v.pos + len(v.raw),
            )
        if v.unit and v.unit != "%" and (f.scope or f.name != "duration"):
            hint = (
                f"; {f.raw} is a position, written without a unit ({f.raw} = 12)"
                if not f.scope
                and f.name
                in ("bar", "end_bar", "beat", "pass", "bar.count", "bar.beat_count")
                else ""
            )
            raise TQLError(
                f"{v.unit}s measure how long a unit lasts - they go with "
                f"duration, as in duration = {v.raw}{hint}",
                v.pos,
                v.pos + len(v.raw),
            )
        if op_t.text == "~" and v.kind not in ("regex", "string", "word", "ref"):
            raise self.err("~ needs a /regular expression/", op_t)
        if op_t.text == "~" and v.kind in ("string", "word"):
            try:  # "Form (" is text, but ~ reads it as a pattern
                re.compile(str(v.value))
            except re.error as exc:
                raise TQLError(
                    f"~ reads {v.raw} as a regular expression, and it is "
                    f"not one ({exc}) - escape it, or use = for plain text",
                    v.pos,
                    v.pos + len(v.raw),
                ) from None
        if v.kind == "range" and op_t.text not in ("=", "!="):
            raise self.err("a range a..b goes with = or !=", op_t)
        return Compare(f, op_t.text, v, False, start)

    def value(self) -> Value:
        t = self.peek()
        if t.type == "STRING":
            self.next()
            return Value("string", t.value, t.text, t.pos)
        if t.type == "REGEX":
            self.next()
            return Value("regex", t.value, t.text, t.pos)
        if t.type == "REF":
            return Value("ref", self.field_ref(), t.text, t.pos)
        if t.type == "WORD" or t.type == "QUANT":
            # glue adjacent pieces back together: `verse?` is a value here, not
            # a step with a quantifier
            self.next()
            raw, end = t.text, t.end
            while self.peek().type in ("WORD", "QUANT") and self.peek().pos == end:
                nt = self.next()
                raw += nt.text
                end = nt.end
            return self.interpret_word(raw, t.pos)
        raise self.err(f"expected a value, found {self.describe(t)}", t)

    def unit_opt(self, v: Value) -> Value:
        """A unit after a number or a range: ``8 bars``, ``7..9 beats``,
        ``30 s``. Seconds become plain numbers; bars and beats stay on the
        value, for ``duration`` to be measured on the beat timeline. Values in
        milliseconds are not part of TQL v0.1.0."""
        u = self.peek()
        if (
            v.kind in ("number", "range")
            and not v.unit
            and u.type == "WORD"
            and u.text == "%"
        ):
            raise self.err(f"write a percentage without a space: {v.raw}%", u)
        if (
            v.kind not in ("number", "range")
            or v.unit
            or u.type != "WORD"
            or u.text.lower() not in _UNITS
        ):
            return v
        if not all(_NUM_RE.match(x.strip()) for x in v.raw.split("..")):
            raise self.err(
                f"a unit goes after a plain number, as in 8 bars - "
                f"not after {v.raw}",
                u,
            )
        self.next()
        unit, raw = _UNITS[u.text.lower()], self.text[v.pos : u.end]
        if unit == "ms":
            raise _not_in_v01(raw, v.pos, u.end)
        if unit in ("bar", "beat"):
            return Value(v.kind, v.value, raw, v.pos, unit)
        return Value(v.kind, v.value, raw, v.pos)

    def distance_opt(self, f: FieldRef, op_t: Tok, v: Value) -> Value:
        """``$2.start + 16 bars``: a time plus or minus a distance,
        in seconds (``+ 10 s``, ``- 1:30``, a plain number), as a percentage of
        the piece (``+ 10%``) or in bars or beats along the beat timeline. The sign may be glued to the amount
        (``-2beats``). Only times take a distance, on both sides: adding bars
        to a printed bar number would miss pickups, "16a" and repeats."""
        t = self.peek()
        if t.type == "QUANT" and t.text == "+":
            sign, rest = 1.0, None
        elif t.type == "WORD" and t.text == "-":
            sign, rest = -1.0, None
        elif (
            t.type == "WORD"
            and len(t.text) > 1
            and t.text[0] in "+-"
            and (t.text[1].isdigit() or t.text[1] == ".")
        ):
            sign, rest = (1.0 if t.text[0] == "+" else -1.0), t.text[1:]
        else:
            return v
        self.next()
        if rest is None:
            a = self.peek()
            if a.type != "WORD":
                raise self.err(
                    f"{t.text} needs a distance after it: a number with a "
                    "unit, as in + 16 bars, + 2 beats or + 10 s",
                    a,
                )
            self.next()
            text, a_pos, a_end = a.text, a.pos, a.end
        else:
            text, a_pos, a_end = rest, t.pos + 1, t.end
        if text[:1] in "+-":
            raise TQLError(f"write the sign once: {t.text} {text[1:]}", t.pos, a_end)
        _refuse_hms_and_ms(text, a_pos, ms=False)
        m = _NUM_UNIT_RE.match(text)
        pm = _PERCENT_RE.match(text)
        if pm:  # a percentage of the piece: a time too
            amount, unit = float(pm.group(1)), "%"
        elif m:
            amount, unit = float(m.group(1)), _UNITS.get(m.group(2).lower())
            if unit is None:
                raise TQLError(
                    f"unknown unit {m.group(2)!r} - one of s, ms, beats, bars",
                    a_pos,
                    a_end,
                )
        else:
            amount, unit = _scalar(text), "s"
            if amount is None:
                raise TQLError(
                    f"a distance is a number with a unit, as in + 16 bars, "
                    f"not {text!r}",
                    a_pos,
                    a_end,
                )
            u = self.peek()
            if _NUM_RE.match(text) and u.type == "WORD" and u.upper not in KEYWORDS:
                if u.text.lower() not in _UNITS:
                    raise self.err(
                        f"unknown unit {u.text!r} - one of s, ms, beats, bars", u
                    )
                self.next()
                unit, a_end = _UNITS[u.text.lower()], u.end
        if unit == "ms":
            amount, unit = amount / 1000, "s"
        for side in (f, v.value):
            if side.scope or side.name not in ("start", "end", "time"):
                hint = (
                    " - a printed bar number is no distance; compare times, as in "
                    "$1.start >= $2.start + 16 bars"
                    if not side.scope and side.name in _BAR_NUMBERS
                    else ""
                )
                raise TQLError(
                    f"a distance is added to a time - start, end or time, "
                    f"not {side.raw}{hint}",
                    side.pos,
                    side.pos + len(side.raw),
                )
        if op_t.text == "~":
            raise self.err("~ compares with a /regular expression/, not a time", op_t)
        return Value(
            "ref", v.value, self.text[v.pos : a_end], v.pos, None, (sign * amount, unit)
        )

    @staticmethod
    def interpret_word(raw: str, pos: int) -> Value:
        if raw == "*":
            return Value("any", None, raw, pos)
        if ".." in raw:
            lo_t, _, hi_t = raw.partition("..")
            _refuse_hms_and_ms(lo_t, pos)
            _refuse_hms_and_ms(hi_t, pos + len(lo_t) + 2)
            lo, hi = _amount(lo_t), _amount(hi_t)
            if lo is None or hi is None:
                raise TQLError(
                    f"a range needs numbers or times on both sides, got {raw!r}",
                    pos,
                    pos + len(raw),
                )
            unit = lo[1] or hi[1]  # 7..9bars: the unit may come once, at the end
            for (_, u), side in ((lo, lo_t), (hi, hi_t)):
                if (
                    unit
                    and u != unit
                    and not (u is None and _NUM_RE.match(side.strip()))
                ):
                    raise TQLError(
                        f"range {raw} mixes units - write it as 7..9 bars",
                        pos,
                        pos + len(raw),
                    )
            if lo[0] > hi[0]:
                raise TQLError(f"range {raw} runs backwards", pos, pos + len(raw))
            return Value("range", (lo[0], hi[0]), raw, pos, unit)
        _refuse_hms_and_ms(raw, pos)
        amt = _amount(raw)
        if amt is not None:
            return Value("number", amt[0], raw, pos, amt[1])
        return Value("word", raw, raw, pos)

    # -- actions ----------------------------------------------------------- #
    def action(self) -> Action:
        arrow = self.next()
        t = self.peek()
        if t.type != "WORD" or t.upper not in VERBS:
            raise self.err(f"expected an action after '->': {', '.join(VERBS)}", t)
        verb = t.upper
        if verb == "DELETE":
            # each matched unit goes - or, when the step named it by a category
            # and its label has others, only that category does
            self.next()
            if self.peek().type != "EOF":
                raise self.err(
                    "DELETE takes nothing after it - narrow the query "
                    "to the units that should go",
                    self.peek(),
                )
            return Action("DELETE", text="DELETE", pos=arrow.pos)
        self.next()
        if verb == "SET":
            assigns = [self.assign()]
            while self.at(","):
                self.next()
                assigns.append(self.assign())
            return Action(
                "SET",
                assigns,
                text=self.text[t.pos : self.peek().pos].strip(),
                pos=arrow.pos,
            )
        return self.edit_action(verb, t, arrow)

    def edit_action(self, verb: str, t: Tok, arrow: Tok) -> Action:
        """GROUP, UNGROUP, TAG and UNTAG; ``t`` is the verb, already consumed.
        TAG and UNTAG may name whose units first: ``$0`` all of the match's,
        ``$n`` those of one step."""
        unit_tok: Tok | None = None
        if verb in ("TAG", "UNTAG") and self.at("REF"):
            unit_tok = self.unit_tok = self.next()
            index, path = unit_tok.value
            if path:
                raise self.err(
                    f"{verb} marks units, not a field: {verb} ${index} " '"..."',
                    unit_tok,
                )
        on_at = next(
            (
                j
                for j in range(self.i, len(self.toks))
                if self.toks[j].type == "WORD" and self.toks[j].upper == "ON"
            ),
            None,
        )
        body_end = len(self.text) if on_at is None else self.toks[on_at].pos
        rest = _flat(self.text[(unit_tok or t).end : body_end])
        action = Action(
            verb,
            text=nfc(_strip_comments(self.text[t.pos :])).strip(),
            pos=arrow.pos,
            unit=None if unit_tok is None else unit_tok.value[0],
        )
        try:
            if verb == "GROUP":
                m = _GROUP_RE.match(rest)
                if not m:
                    raise _EditError(
                        'GROUP expects: GROUP AS "label" [COLOR "#rrggbb"]'
                    )
                action.label = _unquote(m.group("label"), "GROUP AS")
                if not action.label.strip():
                    raise _EditError("GROUP AS needs a non-empty label")
                if m.group("color"):
                    action.color = _unquote(m.group("color"), "COLOR")
            elif verb == "UNGROUP":
                if rest:
                    raise _EditError(f"UNGROUP takes no arguments, got {rest!r}")
            elif verb == "TAG":
                action.tag = _unquote(rest, "TAG")
                if not action.tag.strip():
                    raise _EditError("TAG needs a non-empty value")
            else:
                # `*` clears every tag; a named tag clears only that one. A bare
                # UNTAG is refused rather than assumed to mean `*`: "take this
                # tag off" and "take all tags off" are different intents, and
                # the destructive one has to be spelled out.
                if rest == "*":
                    action.tag = "*"
                else:
                    action.tag = _unquote(rest, "UNTAG")
                    if not action.tag.strip():
                        raise _EditError("UNTAG needs a non-empty value")
            if on_at is not None:
                action.on = self.on_clause(on_at + 1)
                if verb != "GROUP":
                    raise _EditError(
                        "ON only applies to GROUP - the other verbs never "
                        "need a parent slot"
                    )
        except _EditError as exc:
            raise TQLError(str(exc), t.pos, len(self.text)) from None
        self.i = len(self.toks) - 1  # consumed to the end
        return action

    def on_clause(self, first: int) -> list[OnRule]:
        """``free -> INSERT  congruent -> ADD-CATEGORY  …``, from the token at
        ``first`` to the end, one rule per shape, as written. Each shape's text
        runs to the next shape word; a quoted tag holding a shape name is one
        string token, so it never splits a rule."""
        toks = self.toks[first:-1]
        if not toks:
            raise _EditError("ON clause is empty")
        heads = [
            j
            for j, k in enumerate(toks)
            if k.type == "WORD" and k.upper.lower() in _SHAPES
        ]
        if not heads or heads[0] > 0:
            stop = toks[heads[0]].pos if heads else len(self.text)
            raise _EditError(
                f"ON expects a shape name, got "
                f"{_flat(self.text[toks[0].pos:stop])!r} - "
                f"one of {', '.join(_SHAPES)}"
            )
        rules: list[OnRule] = []
        seen: set[str] = set()
        for n, j in enumerate(heads):
            shape = toks[j].upper.lower()
            if shape in seen:
                raise _EditError(f"ON lists {shape!r} twice")
            seen.add(shape)
            stop = toks[heads[n + 1]].pos if n + 1 < len(heads) else len(self.text)
            body = _flat(self.text[toks[j].end : stop])
            if not body.startswith("->"):
                raise _EditError(f"ON {shape} must be followed by '->'")
            head, _, tail = body[2:].strip().partition(" ")
            do = head.strip().upper()
            if do not in _RESOLUTIONS:
                raise _EditError(
                    f"unknown resolution {head.strip()!r} for {shape} - "
                    f"one of {', '.join(_RESOLUTIONS)}"
                )
            tag: str | None = None
            tail = tail.strip()
            if tail:
                kw, _, arg = tail.partition(" ")
                if kw.strip().upper() != "TAG":
                    raise _EditError(f'unexpected {tail!r} after {do} - only TAG "…"')
                if do != "SKIP":
                    raise _EditError("TAG may only follow SKIP")
                tag = _unquote(arg, "TAG")
            rules.append(OnRule(shape, do, tag))
        return rules

    def assign(self) -> Assign:
        f = self.field_ref()
        op = self.expect("OP", "'='")
        if op.text != "=":
            raise self.err("SET assigns with '='", op)
        return Assign(f, self.value())

    # -- checks ------------------------------------------------------------ #
    def check_targets(self, q: Query) -> None:
        """``@`` marks the result among the steps of the query's sequence. A
        relation needs none (its left unit is the result), and units inside
        brackets are tests, never part of a match."""
        p = q.pattern
        if isinstance(p, RelPattern):
            for st in _marked(p.relation.target):
                raise TQLError(_REL_NO_AT, st.pos, st.pos + 1)
        tested = (
            list(_tests_in(p.seq))
            if isinstance(p, SeqPattern)
            else list(_tests(p.left.conds)) + list(_tests_in(p.relation.target))
            if isinstance(p, RelPattern)
            else []
        )
        for seq in tested + list(_tests(q.where)):
            for st in _marked(seq):
                raise TQLError(
                    "@ marks the result among the steps of the query's "
                    "sequence; inside brackets units are only tests",
                    st.pos,
                    st.pos + 1,
                )

    def check_refs(self, q: Query) -> None:
        n = q.slot_count
        refs: list[FieldRef] = []

        def walk_conds(conds: list[Cond], in_where: bool) -> None:
            for c in conds:
                if isinstance(c, Compare):
                    for f in (
                        c.field,
                        c.value.value if c.value.kind == "ref" else None,
                    ):
                        if isinstance(f, FieldRef) and f.index is not None:
                            if not in_where:
                                raise TQLError(
                                    f"{f.raw}: units are numbered for WHERE "
                                    "and actions; inside brackets a "
                                    "condition talks about its own unit",
                                    f.pos,
                                    f.pos + len(f.raw),
                                )
                            refs.append(f)

        def walk_seq(seq: Seq) -> None:
            for st in seq.steps:
                items = [st.item] if isinstance(st.item, Unit) else []
                if isinstance(st.item, Group):
                    for opt in st.item.options:
                        walk_seq(opt)
                for u in items:
                    walk_conds(u.conds, False)
                    for c in u.conds:
                        if isinstance(c, Children):
                            walk_seq(c.seq)
                        elif isinstance(c, RelCond):
                            walk_seq(c.relation.target)

        p = q.pattern
        if isinstance(p, SeqPattern):
            walk_seq(p.seq)
        elif isinstance(p, RelPattern):
            walk_conds(p.left.conds, False)
            walk_seq(p.relation.target)
        for c in q.where:
            if isinstance(c, Children):
                walk_seq(c.seq)
            elif isinstance(c, RelCond):
                walk_seq(c.relation.target)
        walk_conds(q.where, True)
        if q.action:
            for a in q.action.assigns:
                for f in (a.field, a.value.value if a.value.kind == "ref" else None):
                    if isinstance(f, FieldRef) and f.index is not None:
                        refs.append(f)
            if self.unit_tok is not None:
                u = self.unit_tok
                refs.append(FieldRef("", None, u.value[0], u.text, u.pos))
        for f in refs:
            if n == 0:
                raise TQLError(
                    f"{f.raw}: this query has no numbered units",
                    f.pos,
                    f.pos + len(f.raw),
                )
            if f.index == 0:
                continue
            if not 1 <= f.index <= n:
                raise TQLError(
                    f"{f.raw}: a match of this query has {n} unit"
                    f"{'s' if n != 1 else ''} ($1...${n})",
                    f.pos,
                    f.pos + len(f.raw),
                )


_REL_NO_AT = (
    "a relation needs no @ - its left unit is the result; for the other side, "
    "swap them (* IN cadences ENDS ST IN form is the cadence, ST IN form ENDS "
    "WITH * IN cadences the ST)"
)


def _marked(seq: Seq) -> Iterator[Step]:
    """The steps of ``seq`` marked with ``@``, inside its groups too."""
    for st in seq.steps:
        if st.target:
            yield st
        if isinstance(st.item, Group):
            for o in st.item.options:
                yield from _marked(o)


def _tests(conds: list[Cond]) -> Iterator[Seq]:
    """The sequences that bracket conditions test (children, relation targets),
    at any depth: their units are tests, never part of a match."""
    for c in conds:
        seq = (
            c.seq
            if isinstance(c, Children)
            else c.relation.target
            if isinstance(c, RelCond)
            else None
        )
        if seq is not None:
            yield seq
            yield from _tests_in(seq)


def _tests_in(seq: Seq) -> Iterator[Seq]:
    for st in seq.steps:
        if isinstance(st.item, Group):
            for o in st.item.options:
                yield from _tests_in(o)
        else:
            yield from _tests(st.item.conds)


def _joins_units(seq: Seq) -> bool:
    """Whether a match of ``seq`` can hold two units in a row, so that how far
    apart they may be (``THEN … WITHIN``) means something: two steps, or one
    that repeats (``verse+``), or a group with either inside."""
    if len(seq.steps) > 1:
        return True
    st = seq.steps[0]
    if st.hi is None or st.hi > 1:
        return True
    return isinstance(st.item, Group) and any(_joins_units(o) for o in st.item.options)


def _strip_comments(text: str) -> str:
    """``text`` without its ``-- …`` comments, leaving quoted strings alone."""
    out, i, n, quoted = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            quoted = not quoted
        elif (
            not quoted
            and text.startswith("--", i)
            and (i == 0 or text[i - 1].isspace())
        ):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


class _EditError(ValueError):
    """A malformed GROUP, UNGROUP, TAG or UNTAG; becomes a :class:`TQLError`."""


def _flat(text: str) -> str:
    """``text`` without comments, in NFC, its whitespace collapsed to single spaces."""
    return " ".join(nfc(_strip_comments(text)).split())


def _unquote(tok: str, what: str) -> str:
    """Read a double-quoted string; ``\\"`` and ``\\\\`` are the only escapes."""
    m = _STR_RE.fullmatch(tok.strip())
    if not m:
        raise _EditError(f"{what} must be a double-quoted string, got {tok.strip()!r}")
    return m.group(1).replace('\\"', '"').replace("\\\\", "\\")


_HMS_RE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")


def _refuse_hms_and_ms(text: str, pos: int, ms: bool = True) -> None:
    """Raise for ``text`` written as hours:minutes:seconds or, when ``ms`` is
    true, in milliseconds: TQL v0.1.0 has neither as a value."""
    t = text.strip()
    pos += len(text) - len(text.lstrip())
    if _HMS_RE.match(t):
        raise _not_in_v01(t, pos, pos + len(t))
    m = _NUM_UNIT_RE.match(t)
    if ms and m and _UNITS.get(m.group(2).lower()) == "ms":
        raise _not_in_v01(t, pos, pos + len(t))


def _scalar(text: str) -> float | None:
    """A number, a ``m:ss`` time or a ``90s`` / ``500ms`` duration, in seconds;
    ``None`` when ``text`` is none of these."""
    t = text.strip()
    if _NUM_RE.match(t):
        return float(t)
    m = _TIME_RE.match(t)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = _NUM_UNIT_RE.match(t)
    unit = _UNITS.get(m.group(2).lower()) if m else None
    if unit in ("s", "ms"):
        v = float(m.group(1))
        return v / 1000 if unit == "ms" else v
    return None


def _amount(text: str) -> tuple[float, str | None] | None:
    """:func:`_scalar`, plus a length in bars or beats glued to its number
    (``8bars``), or a percentage of the piece (``50%``): ``(seconds, None)``,
    ``(amount, "bar" | "beat")`` or ``(percent, "%")``."""
    s = _scalar(text)
    if s is not None:
        return s, None
    m = _PERCENT_RE.match(text.strip())
    if m:
        return float(m.group(1)), "%"
    m = _NUM_UNIT_RE.match(text.strip())
    unit = _UNITS.get(m.group(2).lower()) if m else None
    if unit in ("bar", "beat"):
        return float(m.group(1)), unit
    return None


def parse(text: str | None) -> Query:
    """Parse query text into a :class:`Query`; raise :class:`TQLError`."""
    if text is None or not text.strip():
        raise TQLError("empty query", 0)
    try:
        return _Parser(text).query()
    except RecursionError:
        raise TQLError("the query nests brackets or groups too deeply", 0) from None


def format_error(text: str, err: TQLError) -> str:
    """The message plus the offending line with a caret under the culprit."""
    if err.pos is None:
        return err.msg
    line_start = text.rfind("\n", 0, err.pos) + 1
    line_end = text.find("\n", err.pos)
    line_end = len(text) if line_end < 0 else line_end
    line = text[line_start:line_end]
    col = err.pos - line_start
    width = max(1, min((err.end or err.pos + 1), line_end) - err.pos)
    return f"{err.msg}\n  {line}\n  {' ' * col}{'^' * width}"
