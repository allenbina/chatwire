"""Minimal cron expression parser and matcher for schedule automation rules.

Five-field cron format (no extended syntax):
  minute  hour  dom  month  dow
  0-59    0-23  1-31  1-12  0-6  (0 = Sunday, 6 = Saturday)

Supported field syntax: ``*``, integer literals, ranges (``1-5``),
comma-separated lists (``1,3,5``), step notation (``*/5``, ``1-5/2``).

No ``@`` shortcuts, no ``L/W/#`` extensions.  Small, auditable, zero
third-party dependencies.
"""
from __future__ import annotations

import datetime
from typing import Tuple

__all__ = ["CronError", "compile_cron", "match_cron"]

# Five-element tuple of frozensets (minute, hour, dom, month, dow).
CompiledCron = Tuple[frozenset, frozenset, frozenset, frozenset, frozenset]


class CronError(ValueError):
    """Raised by :func:`compile_cron` when the expression is invalid."""


def _parse_field(field: str, lo: int, hi: int, name: str) -> frozenset:
    """Parse one cron field into a frozenset of matching integers.

    Args:
        field:  Raw field string (e.g. ``"*/5"``, ``"1,3-5"``, ``"*"``).
        lo:     Minimum allowed value (inclusive).
        hi:     Maximum allowed value (inclusive).
        name:   Field name used in error messages.

    Raises:
        CronError: on syntax or range errors.
    """
    result: set = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronError("Empty token in {!r} field: {!r}".format(name, field))

        if "/" in part:
            # step notation: range/step  or  */step
            slash = part.index("/")
            range_part = part[:slash]
            step_str = part[slash + 1:]
            try:
                step = int(step_str)
            except ValueError:
                raise CronError(
                    "Invalid step {!r} in {} field".format(step_str, name)
                )
            if step <= 0:
                raise CronError(
                    "Step must be >= 1 in {} field, got {}".format(name, step)
                )
            if range_part == "*":
                start, end = lo, hi
            elif "-" in range_part:
                dash = range_part.index("-")
                try:
                    start = int(range_part[:dash])
                    end = int(range_part[dash + 1:])
                except ValueError:
                    raise CronError(
                        "Invalid range {!r} in {} field".format(range_part, name)
                    )
            else:
                try:
                    start = int(range_part)
                except ValueError:
                    raise CronError(
                        "Invalid value {!r} in {} field".format(range_part, name)
                    )
                end = hi
            if not (lo <= start <= hi) or not (lo <= end <= hi):
                raise CronError(
                    "Range {}-{} out of [{},{}] in {} field".format(
                        start, end, lo, hi, name
                    )
                )
            result.update(range(start, end + 1, step))

        elif part == "*":
            result.update(range(lo, hi + 1))

        elif "-" in part:
            dash = part.index("-")
            try:
                start = int(part[:dash])
                end = int(part[dash + 1:])
            except ValueError:
                raise CronError(
                    "Invalid range {!r} in {} field".format(part, name)
                )
            if not (lo <= start <= hi) or not (lo <= end <= hi):
                raise CronError(
                    "Range {}-{} out of [{},{}] in {} field".format(
                        start, end, lo, hi, name
                    )
                )
            result.update(range(start, end + 1))

        else:
            try:
                v = int(part)
            except ValueError:
                raise CronError(
                    "Invalid value {!r} in {} field".format(part, name)
                )
            if not (lo <= v <= hi):
                raise CronError(
                    "Value {} out of [{},{}] in {} field".format(v, lo, hi, name)
                )
            result.add(v)

    return frozenset(result)


def compile_cron(expr: str) -> CompiledCron:
    """Parse a 5-field cron expression and return a compiled tuple.

    The tuple contains five :class:`frozenset` objects in field order:
    ``(minute_set, hour_set, dom_set, month_set, dow_set)``.

    Args:
        expr: A cron expression string with exactly 5 whitespace-separated
              fields, e.g. ``"0 9 * * 1-5"`` (09:00 Mon–Fri).

    Raises:
        CronError: if the expression is empty, has the wrong field count, or
                   contains invalid syntax or out-of-range values.
    """
    if not expr or not expr.strip():
        raise CronError("Cron expression must not be empty")
    parts = expr.strip().split()
    if len(parts) != 5:
        raise CronError(
            "Cron expression must have exactly 5 fields "
            "(minute hour dom month dow), got {}: {!r}".format(len(parts), expr)
        )
    minute_s, hour_s, dom_s, month_s, dow_s = parts
    return (
        _parse_field(minute_s, 0, 59, "minute"),
        _parse_field(hour_s, 0, 23, "hour"),
        _parse_field(dom_s, 1, 31, "dom"),
        _parse_field(month_s, 1, 12, "month"),
        _parse_field(dow_s, 0, 6, "dow"),
    )


def match_cron(compiled: CompiledCron, dt: datetime.datetime) -> bool:
    """Return True when *dt* falls on the *compiled* cron schedule.

    Day-of-week uses the cron convention (0 = Sunday, 6 = Saturday).
    Python's :meth:`~datetime.datetime.weekday` gives 0 = Monday, so the
    conversion is ``cron_dow = (python_weekday + 1) % 7``.

    Args:
        compiled: Result of :func:`compile_cron`.
        dt:       Datetime to test (typically ``datetime.datetime.now()``).
    """
    minute_set, hour_set, dom_set, month_set, dow_set = compiled
    cron_dow = (dt.weekday() + 1) % 7  # Mon=0→1, …, Sun=6→0
    return (
        dt.minute in minute_set
        and dt.hour in hour_set
        and dt.day in dom_set
        and dt.month in month_set
        and cron_dow in dow_set
    )
