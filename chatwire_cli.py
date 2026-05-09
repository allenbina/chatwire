"""chatwire: install / uninstall / inspect the local bridge.

A user-facing wrapper around launchd. Renders the plist templates from
templates/launchd/, drops them into ~/Library/LaunchAgents/, and loads them.
Also bundles a `doctor` subcommand that surfaces TCC and config issues, a
`logs` subcommand that tails launchd output, and `migrate` for the
legacy-.env-to-config.json hop.

Phase 1 scope: this file replaces the ad-hoc shell scripts and the
hand-installed plists. The `setup` subcommand currently just prints the URL
of the (not-yet-built) web wizard; Phase 2 implements the wizard itself.

Usage:
    chatwire setup
    chatwire install-agents
    chatwire uninstall-agents
    chatwire logs [--service bridge|web|all] [-f]
    chatwire doctor
    chatwire migrate
    chatwire uninstall [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import string
import subprocess
import sys
import webbrowser
from pathlib import Path

import _version
import config

DEFAULT_LABEL_PREFIX = "dev.chatwire"
DEFAULT_LOG_DIR = Path.home() / "Library" / "Logs" / "chatwire"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "launchd"

PLIST_NAMES = ("bridge", "web", "keepawake")


def _require_macos() -> None:
    if sys.platform != "darwin":
        sys.exit("chatwire runs on macOS only (the bridge needs chat.db + AppleScript).")


def _warn_non_framework_python() -> None:
    """TCC binds Full Disk Access and Automation grants to the specific Python
    binary, not the venv that wraps it. A pipx install built off Homebrew (or
    any non-python.org) Python will need its OWN re-grant — the user's existing
    grants to python.org's Python won't carry over. Surface this loudly the
    first time they run a subcommand."""
    if sys.platform != "darwin":
        return
    if os.environ.get("CHATWIRE_ALLOW_NON_FRAMEWORK_PYTHON") == "1":
        return
    # sys.base_prefix is the prefix of the interpreter the venv was built off
    # (or sys.prefix when not in a venv) — the public, stable signal for
    # "which Python identity am I really under." sys.base_executable looks
    # tempting but it's a private attribute, missing on some 3.x builds.
    base_prefix = sys.base_prefix
    framework_prefixes = (
        "/Library/Frameworks/Python.framework/",
        "/opt/local/Library/Frameworks/Python.framework/",  # MacPorts
    )
    if any(base_prefix.startswith(p) for p in framework_prefixes):
        return
    msg = (
        f"WARNING: chatwire is running under a Python whose base prefix is\n"
        f"  {base_prefix}\n"
        "which is not python.org's framework Python. macOS TCC tracks each\n"
        "Python binary as a distinct identity, so the Full Disk Access +\n"
        "Automation grants you'll need won't carry over from another install.\n"
        "\n"
        "Recommended: install python.org Python from\n"
        "  https://www.python.org/downloads/macos/\n"
        "and reinstall chatwire with\n"
        "  pipx install --python /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 chatwire\n"
        "\n"
        "Suppress this warning with CHATWIRE_ALLOW_NON_FRAMEWORK_PYTHON=1."
    )
    print(msg, file=sys.stderr)


def _default_install_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_venv_python() -> Path:
    """Return the venv's bin/python<major.minor> (the binary whose sys.path
    includes the chatwire install).

    NOT sys.executable: on macOS framework Python (python.org), the pipx
    venv's bin/python3.X is a symlink/copy of the framework binary, and
    sys.executable returns the *resolved* base path. Plists rendered with
    sys.executable would invoke the base Python and miss the venv's
    site-packages, so the web agent fails on `import fastapi` and the
    bridge runs but sees no integrations (lazy imports mask the same root
    cause).

    Outside a venv, sys.prefix == sys.base_prefix and we just hand back
    sys.executable.
    """
    if sys.prefix != sys.base_prefix:
        venv_bin = Path(sys.prefix) / "bin"
        for name in (f"python{sys.version_info.major}.{sys.version_info.minor}",
                     f"python{sys.version_info.major}",
                     "python"):
            p = venv_bin / name
            if p.exists():
                return p
    return Path(sys.executable)


def _render_template(template: Path, vars: dict[str, str]) -> str:
    return string.Template(template.read_text()).substitute(vars)


def _agent_path(label_prefix: str, name: str) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label_prefix}.{name}.plist"


def _label(label_prefix: str, name: str) -> str:
    return f"{label_prefix}.{name}"


# ---------- subcommands ----------

def cmd_install_agents(args: argparse.Namespace) -> int:
    _require_macos()
    install_dir = Path(args.install_dir).resolve()
    # NOT .resolve() — on macOS framework Python (python.org), the pipx
    # venv's bin/python3.X is a symlink to the framework binary, and
    # resolve() would dereference it. The plist needs the VENV-form path
    # so that Python boots with sys.prefix pointing at the venv (and so
    # finds the venv's site-packages); invoking the framework binary
    # directly skips the venv and the import of fastapi etc. fails.
    venv_python = Path(args.venv_python).absolute()
    log_dir = Path(args.log_dir).resolve()
    label_prefix = args.label_prefix

    if not (install_dir / "bridge.py").exists():
        sys.exit(f"--install-dir {install_dir} doesn't look like the repo (no bridge.py)")
    if not venv_python.exists():
        sys.exit(f"--venv-python {venv_python} doesn't exist")

    log_dir.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    vars = {
        "LABEL_PREFIX": label_prefix,
        "INSTALL_DIR": str(install_dir),
        "VENV_PYTHON": str(venv_python),
        "LOG_DIR": str(log_dir),
    }

    rendered: list[Path] = []
    for name in PLIST_NAMES:
        tpl = TEMPLATE_DIR / f"{name}.plist.template"
        if not tpl.exists():
            sys.exit(f"missing template: {tpl}")
        out = _agent_path(label_prefix, name)
        out.write_text(_render_template(tpl, vars))
        rendered.append(out)
        print(f"wrote {out}")

    for path in rendered:
        # `launchctl load -w` is deprecated on Sequoia+ but still works on 12-15.
        # Switch to bootstrap-domain syntax once the Sequoia minimum is set.
        r = subprocess.run(
            ["launchctl", "load", "-w", str(path)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            # Already loaded → harmless. Anything else worth surfacing.
            stderr = (r.stderr or "").strip()
            if "already loaded" not in stderr.lower():
                print(f"launchctl load failed for {path}: {stderr}", file=sys.stderr)
        else:
            print(f"loaded {path.name}")
    return 0


def cmd_uninstall_agents(args: argparse.Namespace) -> int:
    _require_macos()
    label_prefix = args.label_prefix
    for name in PLIST_NAMES:
        path = _agent_path(label_prefix, name)
        if not path.exists():
            continue
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True, text=True)
        path.unlink()
        print(f"removed {path}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Phase 1 stub: prints the wizard URL. Phase 2 ships the wizard itself."""
    cfg = config.apply_to_environ()
    port = int(cfg.get("WEB_PORT") or os.environ.get("WEB_PORT") or 8723)
    url = f"http://127.0.0.1:{port}/setup"
    print(f"setup wizard (when implemented): {url}")
    print("for now, run `chatwire install-agents` and configure via")
    print(f"~/.chatwire/config.json (chmod 600).")
    if args.open:
        webbrowser.open(url)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    _require_macos()
    log_dir = Path(args.log_dir)
    targets: list[Path] = []
    if args.service in ("bridge", "all"):
        targets.append(log_dir / "stderr.log")
    if args.service in ("web", "all"):
        targets.append(log_dir / "web-stderr.log")
    targets = [t for t in targets if t.exists()]
    if not targets:
        print(f"no log files yet at {log_dir}", file=sys.stderr)
        return 1
    cmd = ["tail"]
    if args.follow:
        cmd.append("-F")
    cmd.append("-n")
    cmd.append(str(args.lines))
    cmd.extend(str(t) for t in targets)
    return subprocess.call(cmd)


def _doctor_color() -> bool:
    """Return True if stdout supports ANSI color codes."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _doctor_ok(label: str, detail: str = "") -> None:
    if _doctor_color():
        mark = "\033[32m✓\033[0m"
    else:
        mark = "✓"
    msg = f"  {mark} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def _doctor_fail(label: str, detail: str = "") -> None:
    if _doctor_color():
        mark = "\033[31m✗\033[0m"
    else:
        mark = "✗"
    msg = f"  {mark} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def _doctor_warn(label: str, detail: str = "") -> None:
    if _doctor_color():
        mark = "\033[33m⚠\033[0m"
    else:
        mark = "⚠"
    msg = f"  {mark} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def run_doctor_checks() -> dict:
    """Run all system pre-flight checks; return a structured result dict.

    Returns::
        {
          "critical_failures": int,
          "checks": [{"label": str, "status": "ok"|"fail"|"warn", "detail": str}, ...]
        }

    Imported by tests and potentially by other modules that need structured
    results rather than printed output.
    """
    from web.probes import probe_fda, probe_automation

    checks = []

    # 1. macOS version (non-critical: warn if missing, info if present)
    if sys.platform == "darwin":
        ver = platform.mac_ver()[0] or "unknown"
        checks.append({"label": "macOS", "status": "ok", "detail": f"version {ver}"})
    else:
        checks.append({
            "label": "macOS",
            "status": "warn",
            "detail": f"not on macOS (platform={sys.platform}) — bridge won't function",
        })

    # 2. Python version >= 3.10 (non-critical: warn)
    vi = sys.version_info
    py_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    if vi >= (3, 10):
        checks.append({"label": "Python", "status": "ok", "detail": f"{py_str} ≥ 3.10"})
    else:
        checks.append({
            "label": "Python",
            "status": "warn",
            "detail": f"{py_str} is below the 3.10 minimum — upgrade Python",
        })

    # 3. Full Disk Access (critical)
    fda = probe_fda()
    checks.append({
        "label": "Full Disk Access",
        "status": fda["status"],
        "detail": fda["detail"],
    })

    # 4. Automation → Messages (critical)
    auto = probe_automation()
    checks.append({
        "label": "Automation → Messages",
        "status": auto["status"],
        "detail": auto["detail"],
    })

    # 5. pipx installed (non-critical)
    pipx_path = shutil.which("pipx")
    if pipx_path:
        checks.append({"label": "pipx", "status": "ok", "detail": pipx_path})
    else:
        checks.append({
            "label": "pipx",
            "status": "warn",
            "detail": "not found — install with `pip install pipx` or `brew install pipx`",
        })

    # 6. sips available (non-critical, macOS-only)
    sips_path = shutil.which("sips")
    if sips_path:
        checks.append({"label": "sips", "status": "ok", "detail": sips_path})
    else:
        checks.append({
            "label": "sips",
            "status": "warn",
            "detail": "not found — thumbnail generation will be skipped (macOS built-in, usually /usr/bin/sips)",
        })

    critical_failures = sum(
        1 for c in checks
        if c["status"] == "fail" and c["label"] in ("Full Disk Access", "Automation → Messages")
    )
    return {"critical_failures": critical_failures, "checks": checks}


def cmd_doctor(args: argparse.Namespace) -> int:
    """System pre-flight check: macOS, Python, TCC permissions, and tools."""
    label_prefix = getattr(args, "label_prefix", DEFAULT_LABEL_PREFIX)

    print("chatwire doctor — system pre-flight\n")

    result = run_doctor_checks()
    for c in result["checks"]:
        s = c["status"]
        if s == "ok":
            _doctor_ok(c["label"], c["detail"])
        elif s == "fail":
            _doctor_fail(c["label"], c["detail"])
        else:
            _doctor_warn(c["label"], c["detail"])

    print()

    # Config check
    if config.CONFIG_PATH.exists():
        mode = config.CONFIG_PATH.stat().st_mode & 0o777
        if mode == 0o600:
            _doctor_ok("config.json", f"{config.CONFIG_PATH} (mode 600)")
        else:
            _doctor_warn("config.json", f"{config.CONFIG_PATH} has mode {oct(mode)} — should be 600")
    elif config.LEGACY_ENV_PATH.exists():
        _doctor_warn("config", f"legacy .env at {config.LEGACY_ENV_PATH} — run `chatwire migrate`")
    else:
        _doctor_warn("config", f"not found — run `chatwire setup` to create it")

    # Agent files + loaded state
    if sys.platform == "darwin":
        for name in PLIST_NAMES:
            path = _agent_path(label_prefix, name)
            if path.exists():
                _doctor_ok(f"agent {name}", str(path.name))
            else:
                _doctor_warn(f"agent {name}", f"not installed at {path}")

        if shutil.which("launchctl"):
            listing = subprocess.run(
                ["launchctl", "list"], capture_output=True, text=True,
            ).stdout
            for name in PLIST_NAMES:
                label = _label(label_prefix, name)
                if label in listing:
                    _doctor_ok(f"loaded {name}", label)
                else:
                    _doctor_warn(f"loaded {name}", f"{label} not in launchctl list")

    print()
    cf = result["critical_failures"]
    if cf == 0:
        print("  all critical checks passed")
    else:
        if _doctor_color():
            print(f"\033[31m  {cf} critical failure(s) — bridge will not function\033[0m")
        else:
            print(f"  {cf} critical failure(s) — bridge will not function")

    return 0 if cf == 0 else 1


def _list_installed_plugins() -> list[str]:
    """Return dist names of pipx-injected plugins (best-effort, empty on error)."""
    import importlib.metadata
    plugins = []
    try:
        eps = importlib.metadata.entry_points(group="chatwire.integrations")
        for ep in eps:
            if ep.dist is None:
                continue
            dist_name = ep.dist.metadata.get("Name", "")
            if dist_name and dist_name.lower() != "chatwire":
                plugins.append(dist_name)
    except Exception:
        pass
    return sorted(set(plugins))


def _uninstall_paths() -> dict[str, Path]:
    """Return the canonical set of paths that cmd_uninstall removes."""
    return {
        "chatwire_dir": Path.home() / ".chatwire",
        "log_dir": Path.home() / "Library" / "Logs" / "chatwire",
        "thumb_cache": Path.home() / ".chatwire" / "thumb_cache",
    }


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Stop services, remove data dirs, and uninstall the chatwire package.

    Use --dry-run to see what would be removed without changing anything.
    """
    dry = args.dry_run
    label_prefix = getattr(args, "label_prefix", DEFAULT_LABEL_PREFIX)
    paths = _uninstall_paths()

    def _say(msg: str) -> None:
        print(msg)

    def _act(description: str, *cmd: str) -> None:
        if dry:
            _say(f"  (dry-run) {description}")
        else:
            _say(f"  {description}")
            subprocess.run(list(cmd), capture_output=True)

    def _rm(path: Path) -> None:
        if dry:
            _say(f"  (dry-run) remove {path}")
        elif path.exists():
            shutil.rmtree(path) if path.is_dir() else path.unlink(missing_ok=True)
            _say(f"  removed {path}")
        else:
            _say(f"  not found (skip): {path}")

    if not dry:
        _require_macos()
        print()
        print("WARNING: This will permanently remove chatwire and all its data.")
        print()
        confirm = input("Type YES to continue: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return 0
        print()

    # Step 1 — stop launchd agents
    _say("==> Step 1: Stopping launchd agents")
    if sys.platform == "darwin" or dry:
        uid = os.getuid() if hasattr(os, "getuid") else 501
        for name in PLIST_NAMES:
            label = _label(label_prefix, name)
            target = f"gui/{uid}/{label}"
            _act(f"launchctl bootout {target}", "launchctl", "bootout", target)

    # Step 2 — remove plist files
    _say("==> Step 2: Removing plist files")
    for name in PLIST_NAMES:
        plist = _agent_path(label_prefix, name)
        _rm(plist)

    # Step 3 — pipx uninstall
    _say("==> Step 3: Uninstalling via pipx")
    pipx_bin = shutil.which("pipx") or str(Path.home() / ".local" / "bin" / "pipx")
    _act(f"pipx uninstall chatwire", pipx_bin, "uninstall", "chatwire")

    # Step 4 — remove ~/.chatwire/
    _say(f"==> Step 4: Removing {paths['chatwire_dir']}/")
    _rm(paths["chatwire_dir"])

    # Step 5 — remove ~/Library/Logs/chatwire/
    _say(f"==> Step 5: Removing {paths['log_dir']}/")
    _rm(paths["log_dir"])

    # Step 6 — thumb cache (inside ~/.chatwire/, noted explicitly)
    _say(f"==> Step 6: Thumbnail cache — covered by step 4")
    if dry:
        _say(f"  (dry-run) would remove {paths['thumb_cache']} (with parent)")

    # Report: what we cannot remove
    print()
    print("=" * 59)
    print(" What chatwire CANNOT remove on your behalf:")
    print("=" * 59)
    print()
    print("  ~/Library/Messages/      — Apple's database (we never write to it)")
    print()
    print("  Homebrew tap:")
    print("    brew untap allenbina/homebrew-tap")
    print()
    print("  Browser saved passwords / cookies — managed by your browser")
    print()
    plugins = _list_installed_plugins()
    if plugins:
        print("  Third-party plugin packages (removed with the venv in step 3,")
        print("  but if you want them elsewhere reinstall separately):")
        for pkg in plugins:
            print(f"    pipx uninject chatwire {pkg}")
    else:
        print("  Third-party plugin packages:")
        print("    None detected (or already removed with the venv in step 3).")
    print()
    print("=" * 59)
    print()

    if not dry:
        print("chatwire uninstall complete.")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Start the MCP stdio server for LLM agent access."""
    # Ensure the repo root is on sys.path so integrations/ is importable.
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from integrations.mcp import run_stdio_server  # noqa: PLC0415
    except ImportError as exc:
        print(f"chatwire mcp: import error: {exc}", file=sys.stderr)
        return 1
    try:
        run_stdio_server()
    except ImportError as exc:
        print(f"chatwire mcp: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    env_ran = config.migrate_legacy_env()
    if env_ran:
        print(f"migrated {config.LEGACY_ENV_PATH} → {config.CONFIG_PATH}")
        print(f"chmod 600 enforced. legacy file left in place — delete after verification.")

    state_copied = config.migrate_state_dir()
    if state_copied:
        print(f"copied {len(state_copied)} state file(s) "
              f"{config.LEGACY_STATE_DIR} → {config.STATE_DIR}: "
              f"{', '.join(state_copied)}")
        print(f"legacy dir left in place — `rm -rf {config.LEGACY_STATE_DIR}` "
              f"after verifying agents are healthy.")

    if env_ran or state_copied:
        return 0
    if config.CONFIG_PATH.exists():
        print(f"already migrated: {config.CONFIG_PATH} exists. nothing to do.")
        return 0
    print(f"nothing to migrate: neither {config.CONFIG_PATH} "
          f"nor {config.LEGACY_ENV_PATH} exist")
    return 1


# ---------- arg parser ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chatwire")
    p.add_argument(
        "--version",
        action="version",
        version=f"chatwire {_version.__version__}",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("install-agents", help="render and load launchd agents")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.add_argument("--install-dir", default=str(_default_install_dir()))
    sp.add_argument("--venv-python", default=str(_default_venv_python()))
    sp.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    sp.set_defaults(func=cmd_install_agents)

    sp = sub.add_parser("uninstall-agents", help="unload and remove launchd agents")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_uninstall_agents)

    sp = sub.add_parser("setup", help="open the web setup wizard")
    sp.add_argument("--no-open", dest="open", action="store_false", default=True)
    sp.set_defaults(func=cmd_setup)

    sp = sub.add_parser("logs", help="tail bridge / web logs")
    sp.add_argument("--service", choices=("bridge", "web", "all"), default="all")
    sp.add_argument("-f", "--follow", action="store_true")
    sp.add_argument("-n", "--lines", type=int, default=50)
    sp.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    sp.set_defaults(func=cmd_logs)

    sp = sub.add_parser("doctor", help="check config + permissions + agent state")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("uninstall", help="stop services, remove data, uninstall package")
    sp.add_argument("--dry-run", action="store_true",
                    help="list what would be removed without changing anything")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_uninstall)

    sp = sub.add_parser("migrate", help="legacy .env → config.json (one-shot)")
    sp.set_defaults(func=cmd_migrate)

    sp = sub.add_parser(
        "mcp",
        help="start MCP stdio server for LLM agent access (requires: pip install mcp)",
    )
    sp.set_defaults(func=cmd_mcp)

    return p


def main() -> int:
    args = build_parser().parse_args()
    _warn_non_framework_python()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
