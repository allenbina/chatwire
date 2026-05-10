"""Single source of truth for the bridge release version.

Bumped at release time. Used by:
  - web/main.py for /healthz and the update-check banner
  - chatwire_cli.py for `--version`
  - pyproject.toml dynamic version

Format: PEP 440-flavored semver. Pre-1.0 dev builds carry a `-dev` suffix
which the update-check JS treats as "skip the check" (no point pinging
GitHub when you cloned from main).
"""
__version__ = "1.11.0"
