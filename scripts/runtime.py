"""Small cross-platform helpers shared by Lvsea gate scripts."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Shared Windows/POSIX command resolution for validation and publication gates."


def executable(name: str) -> str:
    """Resolve .cmd/.exe launchers on Windows without changing user commands."""
    if os.name == "nt":
        for candidate in (f"{name}.cmd", f"{name}.exe", name):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return shutil.which(name) or name


def command(args: list[str]) -> list[str]:
    if not args:
        return args
    return [executable(args[0]), *args[1:]]


def run(
    args: list[str],
    cwd: Path,
    *,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
    else:
        result = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    if check and not result["ok"]:
        detail = result["stderr"] or result["stdout"] or "unknown error"
        raise RuntimeError(f"command failed: {' '.join(args)}\n{detail}")
    return result
