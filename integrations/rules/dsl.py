"""Trigger grammar DSL parser for chatwire automation rules.

Compiles a text expression into a callable that evaluates whether a given
inbound iMessage matches.  Used by :class:`~integrations.rules.RulesEngine`
when a rule carries ``trigger.type = "dsl"``.

Syntax
------
  EXPR      := OR_EXPR
  OR_EXPR   := AND_EXPR ('OR' AND_EXPR)*
  AND_EXPR  := TERM (('AND'?) TERM)*   # AND is optional (implicit)
  TERM      := ['NOT'] ATOM
  ATOM      := '(' EXPR ')' | PREDICATE

  PREDICATE :=
      always               — always matches
    | from:HANDLE          — sender equals HANDLE
    | not_from:HANDLE      — sender does not equal HANDLE
    | contains:VALUE       — message contains VALUE (case-insensitive)
    | exact:VALUE          — message is exactly VALUE (case-insensitive, stripped)
    | regex:VALUE          — message matches regex VALUE (case-insensitive)
    | in:group             — message is in a group chat
    | in:1to1              — message is in a 1-to-1 chat (aliases: dm, direct)
    | group:GUID           — message is in the chat with this exact GUID

  VALUE is a bare word or a "double-quoted string" (supports backslash escapes).

  AND and OR are case-insensitive keywords.  Adjacent predicates without an
  explicit keyword are treated as implicit AND.

Examples
--------
  always
  from:+15551234567
  contains:"hello world" AND in:group
  from:+15551234567 contains:urgent AND NOT in:group
  (contains:hello OR exact:bye) AND NOT from:+15559999999
  regex:"order\\s+#\\d+" AND from:+15551234567
"""
from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

# Evaluator signature: (text, handle_lc, is_group, chat_guid) -> bool
#   text      — stripped original message text (NOT lowercased)
#   handle_lc — sender handle, already lowercased
#   is_group  — True for group chats
#   chat_guid — group GUID, or None for 1:1 messages
Evaluator = Callable[[str, str, bool, Optional[str]], bool]


class DSLError(ValueError):
    """Raised when a DSL expression is syntactically or semantically invalid."""


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(expr: str) -> List[Tuple[str, str]]:
    """Return a list of (kind, value) tokens.

    Kinds: ``AND``, ``OR``, ``NOT``, ``LPAREN``, ``RPAREN``, ``PRED``, ``EOF``.
    """
    tokens: List[Tuple[str, str]] = []
    i = 0
    n = len(expr)

    while i < n:
        # skip whitespace
        while i < n and expr[i].isspace():
            i += 1
        if i >= n:
            break

        ch = expr[i]

        if ch == '(':
            tokens.append(('LPAREN', '('))
            i += 1
            continue

        if ch == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
            continue

        # Read a single token: runs until whitespace or parenthesis,
        # but respects double-quoted strings embedded in predicate values.
        j = i
        in_quote = False
        while j < n:
            if in_quote:
                if expr[j] == '\\' and j + 1 < n:
                    j += 2      # skip escape sequence
                    continue
                if expr[j] == '"':
                    in_quote = False
                j += 1
            else:
                if expr[j] == '"':
                    in_quote = True
                    j += 1
                    continue
                if expr[j].isspace() or expr[j] in '()':
                    break
                j += 1

        raw = expr[i:j]
        i = j

        if not raw:
            continue

        upper = raw.upper()
        if upper == 'AND':
            tokens.append(('AND', 'AND'))
        elif upper == 'OR':
            tokens.append(('OR', 'OR'))
        elif upper == 'NOT':
            tokens.append(('NOT', 'NOT'))
        else:
            tokens.append(('PRED', raw))

    tokens.append(('EOF', ''))
    return tokens


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def _unescape(s: str) -> str:
    """Remove surrounding double-quotes and process backslash escapes."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        inner = s[1:-1]
        return inner.replace('\\"', '"').replace('\\\\', '\\')
    return s


# ---------------------------------------------------------------------------
# Predicate compiler
# ---------------------------------------------------------------------------

def _compile_pred(token_value: str) -> Evaluator:
    """Compile a single PRED token into an :data:`Evaluator` callable.

    Args:
        token_value: raw predicate string, e.g. ``from:+1234`` or ``always``.
    """
    if ':' in token_value:
        key, raw_value = token_value.split(':', 1)
        value = _unescape(raw_value)
    else:
        key = token_value
        value = ''

    key_lc = key.lower()

    if key_lc == 'always':
        return lambda text, h, g, guid: True

    if key_lc == 'contains':
        needle = value.lower()

        def _contains(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return needle in text.lower()

        return _contains

    if key_lc == 'exact':
        needle = value.lower()

        def _exact(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return text.strip().lower() == needle

        return _exact

    if key_lc == 'regex':
        try:
            rx = re.compile(value, re.IGNORECASE)
        except re.error as exc:
            raise DSLError("invalid regex {!r}: {}".format(value, exc)) from exc

        def _regex(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return bool(rx.search(text))

        return _regex

    if key_lc == 'from':
        handle = value.lower()

        def _from(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return h == handle

        return _from

    if key_lc == 'not_from':
        handle = value.lower()

        def _not_from(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return h != handle

        return _not_from

    if key_lc == 'in':
        val_lc = value.lower()
        if val_lc == 'group':
            return lambda text, h, g, guid: g
        if val_lc in ('1to1', 'dm', 'direct'):
            return lambda text, h, g, guid: not g
        raise DSLError(
            "'in' predicate expects 'group' or '1to1', got {!r}".format(value)
        )

    if key_lc == 'group':
        guid_target = value

        def _group_guid(text: str, h: str, g: bool, guid: Optional[str]) -> bool:
            return guid == guid_target

        return _group_guid

    raise DSLError("unknown predicate key {!r}".format(key))


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------

class _Parser:
    """Recursive descent parser that builds a callable from a token list."""

    def __init__(self, tokens: List[Tuple[str, str]]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Tuple[str, str]:
        return self._tokens[self._pos]

    def _consume(self, kind: Optional[str] = None) -> Tuple[str, str]:
        tok = self._tokens[self._pos]
        if kind is not None and tok[0] != kind:
            raise DSLError(
                "expected {}, got {!r} ({!r}) at token position {}".format(
                    kind, tok[0], tok[1], self._pos
                )
            )
        self._pos += 1
        return tok

    def parse(self) -> Evaluator:
        fn = self._parse_or()
        self._consume('EOF')
        return fn

    # EXPR = OR_EXPR
    # OR_EXPR = AND_EXPR ('OR' AND_EXPR)*
    # AND_EXPR = TERM (('AND'?) TERM)*
    # TERM = ['NOT'] ATOM
    # ATOM = '(' EXPR ')' | PRED

    def _parse_or(self) -> Evaluator:
        left = self._parse_and()
        while self._peek()[0] == 'OR':
            self._consume('OR')
            if self._peek()[0] in ('EOF', 'RPAREN'):
                raise DSLError("expected predicate after OR")
            right = self._parse_and()

            def _or(text: str, h: str, g: bool, guid: Optional[str],
                    l: Evaluator = left, r: Evaluator = right) -> bool:
                return l(text, h, g, guid) or r(text, h, g, guid)

            left = _or
        return left

    def _parse_and(self) -> Evaluator:
        left = self._parse_term()
        while True:
            kind = self._peek()[0]
            # Stop at: end of expression, OR, or closing paren
            if kind in ('EOF', 'OR', 'RPAREN'):
                break
            # Explicit AND keyword
            if kind == 'AND':
                self._consume('AND')
                if self._peek()[0] in ('EOF', 'OR', 'RPAREN'):
                    raise DSLError("expected predicate after AND")
            # else: implicit AND — next token is PRED, NOT, or LPAREN
            right = self._parse_term()

            def _and(text: str, h: str, g: bool, guid: Optional[str],
                     l: Evaluator = left, r: Evaluator = right) -> bool:
                return l(text, h, g, guid) and r(text, h, g, guid)

            left = _and
        return left

    def _parse_term(self) -> Evaluator:
        if self._peek()[0] == 'NOT':
            self._consume('NOT')
            if self._peek()[0] in ('EOF', 'OR', 'AND', 'RPAREN'):
                raise DSLError("expected predicate after NOT")
            inner = self._parse_term()  # right-recursive: supports NOT NOT ...

            def _not(text: str, h: str, g: bool, guid: Optional[str],
                     fn: Evaluator = inner) -> bool:
                return not fn(text, h, g, guid)

            return _not
        return self._parse_atom()

    def _parse_atom(self) -> Evaluator:
        tok_kind, tok_val = self._peek()
        if tok_kind == 'LPAREN':
            self._consume('LPAREN')
            fn = self._parse_or()
            self._consume('RPAREN')
            return fn
        if tok_kind == 'PRED':
            self._consume('PRED')
            return _compile_pred(tok_val)
        raise DSLError(
            "expected predicate or '(', got {!r} ({!r})".format(tok_kind, tok_val)
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_dsl(expr: str) -> Evaluator:
    """Parse and compile a DSL expression string into an evaluator callable.

    Returns a callable ``fn(text, handle_lc, is_group, chat_guid) -> bool``
    that evaluates the expression for a given inbound message:

      * ``text``      — stripped original message text (not lowercased)
      * ``handle_lc`` — sender handle, already lowercased
      * ``is_group``  — ``True`` for group-chat messages
      * ``chat_guid`` — group GUID string, or ``None`` for 1:1 messages

    Args:
        expr: DSL expression string, e.g. ``'contains:"hello" AND in:group'``.

    Raises:
        :class:`DSLError`: if the expression is syntactically or semantically
            invalid (unknown predicate, bad regex, missing operand, etc.).
    """
    stripped = expr.strip()
    if not stripped:
        raise DSLError("empty DSL expression")
    tokens = _tokenize(stripped)
    parser = _Parser(tokens)
    return parser.parse()
