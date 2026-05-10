#!/usr/bin/env python3
"""
Migrate all --color-* arbitrary-value Tailwind classes to shadcn standard utilities.
Also updates the legacy bridge var() references in JS strings.

Run from repo root:
    python3 scripts/migrate_color_tokens.py
"""

import re
import sys
from pathlib import Path

# Ordered list of replacements — longer/more specific patterns first to avoid
# partial matches (e.g., --color-sidebar-hover before --color-sidebar).
REPLACEMENTS = [
    # Backgrounds
    ("bg-[--color-sidebar-hover]",     "bg-accent"),
    ("bg-[--color-sidebar-active]",    "bg-accent"),
    ("bg-[--color-sidebar-bg]",        "bg-[--sidebar-bg]"),
    ("bg-[--color-bg-primary]",        "bg-background"),
    ("bg-[--color-bg-secondary]",      "bg-card"),
    ("bg-[--color-bg-tertiary]",       "bg-muted"),
    ("bg-[--color-input-bg]",          "bg-input"),
    ("bg-[--color-msg-me]",            "bg-[--msg-me]"),
    ("bg-[--color-msg-them]",          "bg-[--msg-them]"),
    ("bg-[--color-accent]/10",         "bg-primary/10"),
    ("bg-[--color-accent]/80",         "bg-primary/80"),
    ("bg-[--color-accent]",            "bg-primary"),
    ("bg-[--color-error]",             "bg-destructive"),
    ("bg-[--color-border]",            "bg-border"),

    # Text colors
    ("text-[--color-text-primary]",    "text-foreground"),
    ("text-[--color-text-secondary]",  "text-muted-foreground"),
    ("text-[--color-text-muted]",      "text-muted-foreground"),
    ("text-[--color-accent]",          "text-primary"),
    ("text-[--color-error]",           "text-destructive"),
    ("text-[--color-success]",         "text-[--success]"),
    ("text-[--color-warning]",         "text-[--warning]"),
    ("text-[--color-info]",            "text-[--info]"),

    # Borders
    ("border-[--color-border]",        "border-border"),
    ("border-[--color-accent]",        "border-primary"),
    ("border-[--color-error]",         "border-destructive"),

    # Rings / focus
    ("ring-[--color-accent]",          "ring-primary"),
    ("ring-[--color-border]",          "ring-border"),

    # With state prefixes — cover focus/hover/focus-within/focus-visible variants
    ("hover:bg-[--color-sidebar-hover]",    "hover:bg-accent"),
    ("hover:bg-[--color-bg-secondary]",     "hover:bg-card"),
    ("hover:bg-[--color-bg-tertiary]",      "hover:bg-muted"),
    ("hover:text-[--color-accent]",         "hover:text-primary"),
    ("hover:text-[--color-error]",          "hover:text-destructive"),
    ("hover:border-[--color-accent]",       "hover:border-primary"),
    ("focus:border-[--color-accent]",       "focus:border-primary"),
    ("focus-within:border-[--color-accent]","focus-within:border-primary"),
    ("focus-visible:ring-[--color-accent]", "focus-visible:ring-primary"),

    # JS string values (used for inline styles, not className)
    ("'var(--color-accent)'",          "'hsl(var(--primary))'"),
    ('"var(--color-accent)"',          '"hsl(var(--primary))"'),
]

REPO_ROOT = Path(__file__).parent.parent
TSX_DIRS = [
    REPO_ROOT / "web/frontend/src",
]


def migrate_file(path: Path) -> int:
    original = path.read_text(encoding="utf-8")
    content = original
    changes = 0
    for old, new in REPLACEMENTS:
        count = content.count(old)
        if count:
            content = content.replace(old, new)
            changes += count
    if content != original:
        path.write_text(content, encoding="utf-8")
    return changes


def main():
    total = 0
    for src_dir in TSX_DIRS:
        for path in sorted(Path(str(src_dir)).rglob("*.tsx")):
            n = migrate_file(path)
            if n:
                print(f"  {path} ({n} replacements)")
                total += n
    print(f"\nTotal replacements: {total}")

    # Verify: are any --color-* references left?
    remaining = []
    for src_dir in TSX_DIRS:
        for path in sorted(Path(str(src_dir)).rglob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            lines = [
                f"  {path}:{i+1}: {line.strip()}"
                for i, line in enumerate(text.splitlines())
                if "--color-" in line
            ]
            remaining.extend(lines)

    if remaining:
        print(f"\nRemaining --color-* references ({len(remaining)} lines):")
        for line in remaining:
            print(line)
    else:
        print("\n✓ No --color-* references remain in .tsx files")


if __name__ == "__main__":
    main()
