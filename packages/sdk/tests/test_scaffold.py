"""Tests for the CLI scaffold command (chatwire-plugin init)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from chatwire_sdk.cli import cmd_init, build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scaffold(name: str, tmp_path: Path) -> Path:
    """Run cmd_init and return the root plugin directory."""
    cmd_init(name, tmp_path)
    return tmp_path / name


# ---------------------------------------------------------------------------
# File existence tests
# ---------------------------------------------------------------------------

def test_scaffold_creates_pyproject_toml(tmp_path):
    root = scaffold("hello_world", tmp_path)
    assert (root / "pyproject.toml").exists()


def test_scaffold_creates_plugin_module(tmp_path):
    root = scaffold("hello_world", tmp_path)
    assert (root / "hello_world" / "plugin.py").exists()


def test_scaffold_creates_package_init(tmp_path):
    root = scaffold("hello_world", tmp_path)
    assert (root / "hello_world" / "__init__.py").exists()


def test_scaffold_creates_test_file(tmp_path):
    root = scaffold("hello_world", tmp_path)
    assert (root / "tests" / "test_plugin.py").exists()


def test_scaffold_creates_readme(tmp_path):
    root = scaffold("hello_world", tmp_path)
    assert (root / "README.md").exists()


# ---------------------------------------------------------------------------
# Content correctness tests
# ---------------------------------------------------------------------------

def test_pyproject_contains_name(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "pyproject.toml").read_text()
    assert 'name = "my_plugin"' in content


def test_pyproject_declares_entry_point(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "pyproject.toml").read_text()
    assert "chatwire.plugins" in content
    assert "MyPluginIntegration" in content


def test_plugin_file_imports_sdk(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "my_plugin" / "plugin.py").read_text()
    assert "from chatwire_sdk import BaseIntegration" in content
    assert "@chatwire_plugin" in content


def test_plugin_file_has_correct_class_name(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "my_plugin" / "plugin.py").read_text()
    assert "class MyPluginIntegration(BaseIntegration):" in content


def test_plugin_file_has_name_attribute(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "my_plugin" / "plugin.py").read_text()
    assert 'NAME = "my_plugin"' in content


def test_test_file_imports_plugin_class(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "tests" / "test_plugin.py").read_text()
    assert "from my_plugin.plugin import MyPluginIntegration" in content


def test_readme_contains_name(tmp_path):
    root = scaffold("my_plugin", tmp_path)
    content = (root / "README.md").read_text()
    assert "my_plugin" in content


# ---------------------------------------------------------------------------
# Multi-word names
# ---------------------------------------------------------------------------

def test_scaffold_multiword_name(tmp_path):
    root = scaffold("stats_reporter", tmp_path)
    plugin_content = (root / "stats_reporter" / "plugin.py").read_text()
    assert "class StatsReporterIntegration" in plugin_content
    assert 'NAME = "stats_reporter"' in plugin_content


# ---------------------------------------------------------------------------
# CLI parser tests
# ---------------------------------------------------------------------------

def test_parser_init_subcommand():
    parser = build_parser()
    args = parser.parse_args(["init", "my_plugin"])
    assert args.command == "init"
    assert args.name == "my_plugin"
    assert args.output_dir == "."


def test_parser_init_with_output_dir():
    parser = build_parser()
    args = parser.parse_args(["init", "my_plugin", "--output-dir", "/tmp"])
    assert args.output_dir == "/tmp"


# ---------------------------------------------------------------------------
# Invalid name validation
# ---------------------------------------------------------------------------

def test_invalid_name_starts_with_digit(tmp_path):
    with pytest.raises(SystemExit):
        cmd_init("1bad", tmp_path)


def test_invalid_name_with_hyphen(tmp_path):
    with pytest.raises(SystemExit):
        cmd_init("bad-name", tmp_path)


# ---------------------------------------------------------------------------
# Idempotency — re-running init on existing dir should not raise
# ---------------------------------------------------------------------------

def test_scaffold_idempotent(tmp_path):
    scaffold("hello_world", tmp_path)
    scaffold("hello_world", tmp_path)  # should not raise
    root = tmp_path / "hello_world"
    assert (root / "pyproject.toml").exists()
