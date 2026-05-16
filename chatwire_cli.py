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
    chatwire uninstall [--purge [--dry-run]]
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

PLIST_NAMES = ("bridge", "web")


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

    print()
    print("Keep-awake: chatwire needs your Mac awake to relay messages.")
    print("Without a keep-awake tool, macOS will sleep and you can't chat,")
    print("wire, or chatwire. We recommend Amphetamine (free, Mac App Store):")
    print("https://apps.apple.com/app/amphetamine/id937984704")
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
    """Alias for cmd_init (kept for backward compat)."""
    return cmd_init(args)


def _generate_vapid_keypair() -> tuple[str, str]:
    """Return (private_b64url, public_b64url) for VAPID web push keys.

    Private key is DER-encoded PKCS8, base64url-no-pad.
    Public key is raw uncompressed P-256 point, base64url-no-pad.
    """
    import base64
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    priv_der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    priv_b64url = base64.urlsafe_b64encode(priv_der).rstrip(b"=").decode()
    pub_b64url = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    return priv_b64url, pub_b64url


def cmd_init(args: argparse.Namespace) -> int:
    """Interactive first-run wizard: prompts for handles, generates VAPID keys,
    writes ~/.chatwire/config.json, and optionally installs launchd agents."""

    # 1. Check for existing config
    if config.CONFIG_PATH.exists():
        ans = input("Config already exists. Re-run setup? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return 0

    # 2. Prompt for self handles
    raw = input("Enter your phone number(s) or Apple ID email(s), comma-separated: ").strip()
    if not raw:
        print("Error: at least one handle is required.", file=sys.stderr)
        return 1
    self_handles = [h.strip() for h in raw.split(",") if h.strip()]
    if not self_handles:
        print("Error: at least one handle is required.", file=sys.stderr)
        return 1

    # 3. Generate VAPID keys
    try:
        vapid_private, vapid_public = _generate_vapid_keypair()
    except Exception as exc:
        print(f"Warning: VAPID key generation failed ({exc}); push notifications won't work.", file=sys.stderr)
        vapid_private = ""
        vapid_public = ""

    # 4. Build and write config
    cfg = {
        "version": config.CURRENT_VERSION,
        "self_handles": self_handles,
        "web": {
            "port": 8723,
            "vapid": {
                "private": vapid_private,
                "public": vapid_public,
                "contact": "mailto:admin@example.com",
            },
        },
    }
    config.save_config(cfg)
    print(f"Config written to {config.CONFIG_PATH}")

    # 5. Offer to install launchd agents (macOS only)
    if sys.platform == "darwin":
        agent_ans = input("Install launchd agents now? [Y/n] ").strip().lower()
        if agent_ans in ("", "y", "yes"):
            # Build a minimal namespace matching what cmd_install_agents expects
            agent_args = argparse.Namespace(
                install_dir=str(_default_install_dir()),
                venv_python=str(_default_venv_python()),
                log_dir=str(DEFAULT_LOG_DIR),
                label_prefix=DEFAULT_LABEL_PREFIX,
            )
            cmd_install_agents(agent_args)
        else:
            print()
            print("Keep-awake: chatwire needs your Mac awake to relay messages.")
            print("Without a keep-awake tool, macOS will sleep and you can't chat,")
            print("wire, or chatwire. We recommend Amphetamine (free, Mac App Store):")
            print("https://apps.apple.com/app/amphetamine/id937984704")
    else:
        print()
        print("Keep-awake: chatwire needs your Mac awake to relay messages.")
        print("Without a keep-awake tool, macOS will sleep and you can't chat,")
        print("wire, or chatwire. We recommend Amphetamine (free, Mac App Store):")
        print("https://apps.apple.com/app/amphetamine/id937984704")

    # 6. Final instructions
    print()
    print("Run `chatwire doctor` to verify your setup.")
    print("Web UI will be available at http://localhost:8723 once services start.")
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

    # 3. MCP package (informational)
    try:
        import mcp as _mcp  # noqa: F401, PLC0415
        checks.append({"label": "MCP package", "status": "ok", "detail": "installed"})
    except ImportError:
        checks.append({
            "label": "MCP package",
            "status": "info",
            "detail": "not installed — install with: pip install 'chatwire[mcp]'",
        })

    # 4. Full Disk Access (critical)
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
        "img_cache": Path.home() / ".chatwire" / "img_cache",
    }


def _purge_item(dry: bool, label: str, action_fn) -> bool:
    """Prompt the user [y/N] for one purge item. Returns True if action taken."""
    if dry:
        print(f"  (dry-run) would remove {label}")
        return False
    ans = input(f"  Remove {label}? [y/N] ").strip().lower()
    if ans == "y":
        action_fn()
        print(f"    → removed {label}")
        return True
    return False


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall chatwire, optionally removing config and data.

    Without --purge: prints instructions for removing the package.
    With --purge: prompts for each data item to delete individually.
    Use --purge --dry-run to preview what would be removed.
    """
    purge = getattr(args, "purge", False)
    dry = getattr(args, "dry_run", False)
    label_prefix = getattr(args, "label_prefix", DEFAULT_LABEL_PREFIX)

    if not purge:
        # Non-destructive: just print removal instructions.
        print("To remove chatwire, run:")
        print("  pipx uninstall chatwire")
        print("  — or —")
        print("  brew uninstall chatwire")
        print()
        print(f"Config and data at ~/.chatwire/ is preserved.")
        print("To also remove config and data interactively, run:")
        print("  chatwire uninstall --purge")
        return 0

    # --- Purge mode ---
    chatwire_dir = Path.home() / ".chatwire"
    log_dir = Path.home() / "Library" / "Logs" / "chatwire"

    if dry:
        print("chatwire uninstall --purge --dry-run (nothing will be changed)\n")
    else:
        print("chatwire uninstall --purge")
        print("Each item below will ask for confirmation before removal.\n")

    # 1. Config
    config_path = chatwire_dir / "config.json"
    _purge_item(dry, f"config ({config_path})", lambda: config_path.unlink(missing_ok=True))

    # 2. Plugins
    plugins_dir = chatwire_dir / "plugins"
    _purge_item(dry, f"plugins ({plugins_dir})",
                lambda: shutil.rmtree(plugins_dir, ignore_errors=True))

    # 3. Read state
    read_state_path = chatwire_dir / "read_state.db"
    _purge_item(dry, f"read state ({read_state_path})",
                lambda: read_state_path.unlink(missing_ok=True))

    # 4. Logs
    jsonl_files = list(chatwire_dir.glob("*.jsonl")) if chatwire_dir.exists() else []
    if jsonl_files:
        _purge_item(
            dry,
            f"logs ({len(jsonl_files)} .jsonl file(s) in {chatwire_dir})",
            lambda: [f.unlink(missing_ok=True) for f in jsonl_files],
        )
    else:
        if dry:
            print(f"  (dry-run) no .jsonl log files found in {chatwire_dir}")

    # 5. LaunchAgents
    plist_paths = [_agent_path(label_prefix, name) for name in PLIST_NAMES]
    existing_plists = [p for p in plist_paths if p.exists()]
    if existing_plists or dry:
        uid = os.getuid() if hasattr(os, "getuid") else 501

        def _remove_agents() -> None:
            for plist in plist_paths:
                label = _label(label_prefix, plist.stem.split(".")[-1])
                subprocess.run(
                    ["launchctl", "bootout", f"gui/{uid}/{label}"],
                    capture_output=True,
                )
                plist.unlink(missing_ok=True)

        _purge_item(
            dry,
            f"LaunchAgents ({label_prefix}.*)",
            _remove_agents,
        )
    else:
        if dry:
            print(f"  (dry-run) no LaunchAgent plists found for {label_prefix}.*")

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
        print("  Third-party plugin packages:")
        for pkg in plugins:
            print(f"    pipx uninject chatwire {pkg}")
    else:
        print("  Third-party plugin packages:")
        print("    None detected.")
    print()
    print("  To remove the package itself:")
    print("    pipx uninstall chatwire")
    print("    — or —")
    print("    brew uninstall chatwire")
    print()
    print("=" * 59)
    print()

    if not dry:
        print("Done. Run `pipx uninstall chatwire` or `brew uninstall chatwire` to remove the package.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Print a summary of the local chatwire installation.

    Shows version, config location, web port, running launchd agents (macOS
    only), and installed plugins. Exits 0 always — this is a read-only probe.
    """
    label_prefix = getattr(args, "label_prefix", DEFAULT_LABEL_PREFIX)

    print(f"chatwire {_version.__version__}")
    print()

    # Config and port
    if config.CONFIG_PATH.exists():
        try:
            cfg = config.load_config()
        except Exception:
            cfg = {}
        port = cfg.get("web", {}).get("port", 8723)
        print(f"Config:  {config.CONFIG_PATH}")
        print(f"Port:    {port}")
    else:
        print(f"Config:  not found — run `chatwire setup`")

    print()

    # LaunchAgents (macOS only)
    if sys.platform == "darwin":
        print("Agents:")
        for name in PLIST_NAMES:
            path = _agent_path(label_prefix, name)
            mark = "✓" if path.exists() else "✗"
            print(f"  {mark} {name:12s}  {path.name}")
        print()

    # Installed plugins
    plugins = _list_installed_plugins()
    if plugins:
        print(f"Plugins ({len(plugins)}):")
        for pkg in plugins:
            print(f"  • {pkg}")
    else:
        print("Plugins: none installed")

    print()
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Start the MCP stdio server for LLM agent access."""
    # Ensure the repo root is on sys.path so integrations/ is importable.
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from integrations.mcp import run_stdio_server  # noqa: PLC0415
    except ImportError:
        print("chatwire mcp: MCP support requires the 'mcp' package.", file=sys.stderr)
        print("Install it with: pip install 'chatwire[mcp]'", file=sys.stderr)
        return 1
    try:
        run_stdio_server()
    except ImportError as exc:
        print(f"chatwire mcp: {exc}", file=sys.stderr)
        print("Install with: pip install 'chatwire[mcp]'", file=sys.stderr)
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
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("install-agents", help="render and load launchd agents")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.add_argument("--install-dir", default=str(_default_install_dir()))
    sp.add_argument("--venv-python", default=str(_default_venv_python()))
    sp.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    sp.set_defaults(func=cmd_install_agents)

    sp = sub.add_parser("uninstall-agents", help="unload and remove launchd agents")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_uninstall_agents)

    sp = sub.add_parser("init", help="first-run setup wizard")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("setup", help="alias for init (first-run setup wizard)")
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

    sp = sub.add_parser("uninstall", help="remove chatwire config and data (see also: --purge)")
    sp.add_argument(
        "--purge",
        action="store_true",
        help="interactively remove config, plugins, read state, logs, and LaunchAgents",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="(with --purge) show what would be removed without changing anything",
    )
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_uninstall)

    sp = sub.add_parser("migrate", help="legacy .env → config.json (one-shot)")
    sp.set_defaults(func=cmd_migrate)

    sp = sub.add_parser("status", help="show installation summary (version, config, agents, plugins)")
    sp.add_argument("--label-prefix", default=DEFAULT_LABEL_PREFIX)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser(
        "mcp",
        help="start MCP stdio server for LLM agent access (requires: pip install mcp)",
    )
    sp.set_defaults(func=cmd_mcp)

    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd is None:
        if not config.CONFIG_PATH.exists():
            print("No config found. Run `chatwire init` to set up chatwire.")
        else:
            build_parser().print_help()
        return 1
    _warn_non_framework_python()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
