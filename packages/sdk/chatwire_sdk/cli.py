"""CLI for the chatwire Plugin SDK.

Entry point: ``chatwire-plugin``

Commands
--------
chatwire-plugin init <name>
    Scaffold a new plugin directory in the current working directory.

    Creates:
        <name>/
            pyproject.toml          — PEP 517 package metadata
            <name>/__init__.py      — Plugin class using BaseIntegration
            tests/test_plugin.py    — Basic smoke test
            README.md               — Plugin documentation stub

Example::

    $ chatwire-plugin init my_greeter
    Scaffolded plugin 'my_greeter' in ./my_greeter/
    Next steps:
      cd my_greeter
      pip install -e ".[dev]"
      pytest
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Scaffolding templates
# ---------------------------------------------------------------------------

_PYPROJECT_TOML = """\
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "{name}"
version = "0.1.0"
description = "A chatwire plugin"
requires-python = ">=3.11"
license = {{ text = "MIT" }}
dependencies = ["chatwire-sdk>=0.1"]

[project.entry-points."chatwire.plugins"]
{name} = "{pkg}.plugin:{class_name}"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[tool.setuptools.packages.find]
where = ["."]
include = ["{pkg}*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
"""

_PLUGIN_INIT = """\
\"\"\"
{class_name} — a chatwire plugin.

Configuration block (in config.json under ``integrations.{name}``):

    {{
        "enabled": true
    }}
\"\"\"
from __future__ import annotations

from typing import Any
from chatwire_sdk import BaseIntegration, PluginManifest, chatwire_plugin


@chatwire_plugin
class {class_name}(BaseIntegration):
    NAME = "{name}"
    DISPLAY_NAME = "{display_name}"
    DESCRIPTION = "A chatwire plugin scaffolded by chatwire-sdk."
    VERSION = "0.1.0"
    AUTHOR = ""

    SETTINGS_SCHEMA = {{
        "type": "object",
        "properties": {{
            "enabled": {{
                "type": "boolean",
                "default": False,
                "title": "Enable {display_name}",
            }},
        }},
    }}

    async def on_startup(self) -> None:
        print(f"[{name}] Plugin started!")

    async def on_shutdown(self) -> None:
        print(f"[{name}] Plugin stopped.")

    async def on_message_received(self, msg: Any) -> None:
        # msg.text, msg.handle, msg.is_from_me, msg.chat_guid
        pass

    async def on_message_sent(self, msg: Any) -> None:
        pass
"""

_TEST_PLUGIN = """\
\"\"\"Smoke tests for {class_name}.\"\"\"
import pytest
from {pkg}.plugin import {class_name}


def test_manifest():
    manifest = {class_name}.manifest()
    assert manifest.name == "{name}"
    assert manifest.version == "0.1.0"
    assert manifest.description


def test_instantiates():
    plugin = {class_name}(config={{"enabled": True}})
    assert plugin.config["enabled"] is True


@pytest.mark.asyncio
async def test_lifecycle_noop():
    plugin = {class_name}()
    await plugin.on_startup()
    await plugin.on_shutdown()


@pytest.mark.asyncio
async def test_on_message_received_noop():
    plugin = {class_name}()

    class FakeMsg:
        text = "hello"
        handle = "+15550000000"
        is_from_me = False
        chat_guid = None

    await plugin.on_message_received(FakeMsg())
"""

_README = """\
# {display_name}

A chatwire plugin.

## Installation

```bash
pip install -e .
```

## Configuration

Add the following to your `config.json` under `integrations`:

```json
"{name}": {{
    "enabled": true
}}
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Lifecycle hooks

| Hook | Description |
|------|-------------|
| `on_startup()` | Called when the chatwire bridge starts |
| `on_shutdown()` | Called when the bridge stops |
| `on_message_received(msg)` | Called for each inbound iMessage |
| `on_message_sent(msg)` | Called after each outbound send |
"""


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _to_class_name(name: str) -> str:
    """Convert snake_case name to CamelCase class name."""
    return "".join(word.capitalize() for word in name.split("_")) + "Integration"


def _to_display_name(name: str) -> str:
    return name.replace("_", " ").title()


def cmd_init(name: str, output_dir: Path) -> None:
    """Scaffold a new plugin in ``output_dir / name``."""
    # Validate name
    if not name.replace("_", "").isalnum() or name[0].isdigit():
        print(
            f"Error: plugin name must be a valid Python identifier, got {name!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    pkg = name  # Python package name mirrors plugin name
    class_name = _to_class_name(name)
    display_name = _to_display_name(name)

    root = output_dir / name
    pkg_dir = root / pkg
    tests_dir = root / "tests"

    for d in (root, pkg_dir, tests_dir):
        d.mkdir(parents=True, exist_ok=True)

    fmt = dict(name=name, pkg=pkg, class_name=class_name, display_name=display_name)

    (root / "pyproject.toml").write_text(
        textwrap.dedent(_PYPROJECT_TOML.format(**fmt)), encoding="utf-8"
    )
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "plugin.py").write_text(
        textwrap.dedent(_PLUGIN_INIT.format(**fmt)), encoding="utf-8"
    )
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_plugin.py").write_text(
        textwrap.dedent(_TEST_PLUGIN.format(**fmt)), encoding="utf-8"
    )
    (root / "README.md").write_text(
        textwrap.dedent(_README.format(**fmt)), encoding="utf-8"
    )

    print(f"Scaffolded plugin '{name}' in {root}/")
    print("Next steps:")
    print(f"  cd {name}")
    print('  pip install -e ".[dev]"')
    print("  pytest")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatwire-plugin",
        description="chatwire Plugin SDK CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    init_p = sub.add_parser("init", help="Scaffold a new plugin")
    init_p.add_argument("name", help="Plugin name (snake_case, e.g. my_greeter)")
    init_p.add_argument(
        "--output-dir",
        default=".",
        metavar="DIR",
        help="Parent directory for the scaffolded plugin (default: current dir)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        cmd_init(args.name, Path(args.output_dir).resolve())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
