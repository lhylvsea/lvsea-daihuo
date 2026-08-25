#!/usr/bin/env python3
"""Validate the Lvsea governed agent-skill package contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

REQUIRED_ROOT_FILES = ("SKILL.md", "README.md", "agents/interface.yaml", "manifest.json")
REQUIRED_MANIFEST_FIELDS = ("name", "version", "owner", "updated_at", "status", "maturity_tier")
REQUIRED_INTERFACE_FIELDS = ("display_name", "short_description", "default_prompt")
IGNORED_DISCOVERY_DIRS = {".git", "dist", "node_modules", "__pycache__", ".agents", ".codex"}
EVIDENCE_TIERS = {"production", "library", "governed"}
MAX_PRODUCTION_SKILL_BYTES = 14_000


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(read_text(path))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        return {}
    payload = yaml.safe_load(read_text(path)) or {}
    return payload if isinstance(payload, dict) else {}


def parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return {}
    block = "\n".join(lines[1:end])
    if yaml is not None:
        payload = yaml.safe_load(block) or {}
        return payload if isinstance(payload, dict) else {}
    data: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip("'\"")
    return data


def discover_skill_entrypoints(root: Path) -> list[str]:
    entries: list[str] = []
    for path in root.rglob("SKILL.md"):
        relative = path.relative_to(root)
        if any(part in IGNORED_DISCOVERY_DIRS for part in relative.parts):
            continue
        entries.append(relative.as_posix())
    return sorted(entries)


def local_markdown_links(text: str) -> list[str]:
    links = re.findall(r"\]\(([^)]+)\)", text)
    output = []
    for link in links:
        clean = link.split("#", 1)[0].strip()
        if clean.endswith(".md") and not clean.startswith(("http://", "https://")):
            output.append(clean)
    return output


def check_readme(root: Path, warnings: list[str]) -> None:
    path = root / "README.md"
    if not path.is_file():
        return
    text = read_text(path)
    checks = {
        "install command": "npx skills add" in text,
        "natural trigger examples": "你可以这样说" in text,
        "verification command": "validate_skill.py" in text,
        "prerequisite checklist": "运行前准备" in text,
        "troubleshooting": "排错" in text or "Troubleshooting" in text,
        "risk boundary": "重要边界" in text or "风险" in text,
        "upstream credit": "lvsea-zao-skill" in text and "source-map.md" in text,
    }
    for label, ok in checks.items():
        if not ok:
            warnings.append(f"README may be missing {label}")


def validate_evidence(root: Path, manifest: dict[str, Any], failures: list[str], warnings: list[str]) -> None:
    tier = str(manifest.get("maturity_tier", "")).lower()
    if tier not in EVIDENCE_TIERS:
        return
    required = (
        "reports/skill-ir.json",
        "reports/trigger-eval.json",
        "reports/prior-art-research.md",
        "reports/creation-handoff.md",
    )
    for relative in required:
        if not (root / relative).is_file():
            failures.append(f"{tier} package missing evidence artifact: {relative}")
    ir_path = root / "reports/skill-ir.json"
    if ir_path.is_file():
        try:
            package = load_json(ir_path).get("package", {})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{ir_path}: invalid evidence JSON: {exc}")
            package = {}
        if package.get("name") != manifest.get("name"):
            failures.append("reports/skill-ir.json package.name does not match manifest.json")
        if package.get("version") != manifest.get("version"):
            failures.append("reports/skill-ir.json package.version does not match manifest.json")
    trigger_path = root / "reports/trigger-eval.json"
    if trigger_path.is_file():
        try:
            trigger = load_json(trigger_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{trigger_path}: invalid evidence JSON: {exc}")
            trigger = {}
        summary = trigger.get("summary", {})
        if trigger.get("ok") is not True or summary.get("total", 0) <= 0 or summary.get("passed") != summary.get("total"):
            failures.append("reports/trigger-eval.json is not passing all cases")
    output = root / "reports/output-evidence.json"
    if not output.is_file():
        warnings.append("reports/output-evidence.json missing; output/provider evidence remains missing evidence")


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    failures: list[str] = []
    warnings: list[str] = []
    manifest: dict[str, Any] = {}

    for relative in REQUIRED_ROOT_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing required file: {relative}")

    entries = discover_skill_entrypoints(root)
    nested = [entry for entry in entries if entry != "SKILL.md"]
    if nested:
        failures.append("nested discoverable SKILL.md entrypoints found: " + ", ".join(nested))

    skill_path = root / "SKILL.md"
    skill_bytes = 0
    frontmatter: dict[str, Any] = {}
    if skill_path.is_file():
        skill_text = read_text(skill_path)
        skill_bytes = len(skill_text.encode("utf-8"))
        frontmatter = parse_frontmatter(skill_text)
        for field in ("name", "description"):
            if not frontmatter.get(field):
                failures.append(f"SKILL.md missing frontmatter field: {field}")
        if frontmatter.get("name") != "lvsea-daihuo":
            failures.append("SKILL.md frontmatter name must be lvsea-daihuo")
        for link in local_markdown_links(skill_text):
            if not (root / link).exists():
                failures.append(f"SKILL.md links to missing reference: {link}")
        if re.search(r"(?:C:\\Users\\|/Users/|/home/|-----BEGIN .*PRIVATE KEY-----)", skill_text, re.I):
            failures.append("SKILL.md contains a private absolute path or private-key marker")

    interface_path = root / "agents/interface.yaml"
    if interface_path.is_file():
        interface = load_yaml(interface_path)
        meta = interface.get("interface", {}) if isinstance(interface, dict) else {}
        compatibility = interface.get("compatibility", {}) if isinstance(interface, dict) else {}
        for field in REQUIRED_INTERFACE_FIELDS:
            if not meta.get(field):
                failures.append(f"agents/interface.yaml missing interface.{field}")
        targets = compatibility.get("adapter_targets", [])
        if not isinstance(targets, list) or not targets:
            failures.append("agents/interface.yaml missing compatibility.adapter_targets")

    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"manifest.json: invalid JSON: {exc}")
        for field in REQUIRED_MANIFEST_FIELDS:
            if not manifest.get(field):
                failures.append(f"manifest.json missing field: {field}")
        if manifest.get("name") != frontmatter.get("name"):
            failures.append("manifest.json name does not match SKILL.md frontmatter")
        if manifest.get("version") and not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest["version"])):
            failures.append("manifest.json version must be semantic X.Y.Z")
        if str(manifest.get("maturity_tier", "")).lower() == "governed":
            for field in ("review_due", "review_cadence", "release_gates"):
                if not manifest.get(field):
                    failures.append(f"governed manifest missing field: {field}")
        if skill_bytes > MAX_PRODUCTION_SKILL_BYTES and manifest.get("context_budget_tier") == "production":
            warnings.append(f"SKILL.md exceeds production context budget: {skill_bytes} > {MAX_PRODUCTION_SKILL_BYTES} bytes")

    check_readme(root, warnings)
    validate_evidence(root, manifest, failures, warnings)

    cases_path = root / "evals/trigger_cases.json"
    if cases_path.is_file():
        try:
            cases = load_json(cases_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"evals/trigger_cases.json: invalid JSON: {exc}")
            cases = {}
        for bucket in ("should_trigger", "should_not_trigger", "near_neighbor", "adversarial"):
            if not cases.get(bucket):
                warnings.append(f"evals/trigger_cases.json has no {bucket} cases")
    else:
        failures.append("missing required evidence input: evals/trigger_cases.json")

    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for script in sorted(scripts_dir.glob("*.py")):
            if script.name.startswith("__"):
                continue
            text = read_text(script)
            if "argparse" not in text and 'SCRIPT_INTERFACE = "internal-module"' not in text:
                warnings.append(f"script has no argparse help or internal-module marker: {script.name}")

    return {"ok": not failures, "root": root.name, "failures": failures, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Lvsea governed agent-skill package.")
    parser.add_argument("skill_dir", nargs="?", default=".")
    args = parser.parse_args()
    result = validate(Path(args.skill_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
