#!/usr/bin/env python3
"""Measure root instructions and on-demand resources without executing them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BUDGETS = {
    "scaffold": {"root_warn": 10_000, "root_block": 16_000},
    "production": {"root_warn": 14_000, "root_block": 20_000},
    "library": {"root_warn": 16_000, "root_block": 24_000},
    "governed": {"root_warn": 18_000, "root_block": 26_000},
}


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def measure(root: Path) -> dict[str, Any]:
    manifest = load_manifest(root)
    tier = str(manifest.get("context_budget_tier") or manifest.get("maturity_tier") or "production").lower()
    budget = BUDGETS.get(tier, BUDGETS["production"])
    root_path = root / "SKILL.md"
    root_bytes = root_path.stat().st_size if root_path.is_file() else 0
    folders: dict[str, int] = {}
    files: list[dict[str, Any]] = []
    for folder in ("references", "scripts", "evals", "reports"):
        total = 0
        target = root / folder
        if target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file() or path.name.endswith((".pyc", ".pyo")):
                    continue
                size = path.stat().st_size
                total += size
                files.append({"path": path.relative_to(root).as_posix(), "bytes": size, "on_demand": folder in {"references", "reports"}})
        folders[folder] = total
    if not root_path.is_file():
        status = "block"
        reason = "SKILL.md missing"
    elif root_bytes > budget["root_block"]:
        status = "block"
        reason = f"root SKILL.md is {root_bytes} bytes; block threshold is {budget['root_block']}"
    elif root_bytes > budget["root_warn"]:
        status = "warn"
        reason = f"root SKILL.md is {root_bytes} bytes; recommended threshold is {budget['root_warn']}"
    else:
        status = "pass"
        reason = f"root SKILL.md is {root_bytes} bytes within {tier} budget"
    return {
        "ok": status != "block",
        "status": status,
        "reason": reason,
        "tier": tier,
        "root_skill_bytes": root_bytes,
        "root_budget_bytes": budget,
        "resource_bytes": folders,
        "total_measured_bytes": root_bytes + sum(folders.values()),
        "files": files,
        "missing_evidence": "context size does not prove output quality or runtime performance",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Lvsea Skill context budget.")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    root = Path(args.skill_dir).resolve()
    result = measure(root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
