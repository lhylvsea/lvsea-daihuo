#!/usr/bin/env python3
"""Export a platform-neutral Skill IR with Yao-style governance fields."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

SCHEMA_VERSION = "3.0.0-lvsea"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(read(path))
    return payload if isinstance(payload, dict) else {}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file() or yaml is None:
        return {}
    payload = yaml.safe_load(read(path)) or {}
    return payload if isinstance(payload, dict) else {}


def frontmatter_and_body(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines()
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return {}, text
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).lstrip()
    if yaml is not None:
        payload = yaml.safe_load(block) or {}
        return (payload if isinstance(payload, dict) else {}), body
    result: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("'\"")
    return result, body


def sections(body: str) -> dict[str, str]:
    result: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            result[current] = []
        else:
            result.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in result.items()}


def list_items(text: str, limit: int = 40) -> list[str]:
    output: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)$", line)
        if match and match.group(1).strip():
            output.append(match.group(1).strip())
        if len(output) >= limit:
            break
    return output


def files(root: Path, folder: str) -> list[str]:
    target = root / folder
    if not target.is_dir():
        return []
    return [path.relative_to(root).as_posix() for path in sorted(target.rglob("*")) if path.is_file() and "__pycache__" not in path.parts]


def trigger_samples(root: Path, bucket: str) -> list[str]:
    cases = load_json(root / "evals/trigger_cases.json")
    output: list[str] = []
    for item in cases.get(bucket, []):
        if isinstance(item, str):
            output.append(item)
        elif isinstance(item, dict) and item.get("text"):
            output.append(str(item["text"]))
    return output


def build_ir(root: Path) -> dict[str, Any]:
    root = root.resolve()
    frontmatter, body = frontmatter_and_body(read(root / "SKILL.md"))
    section_map = sections(body)
    manifest = load_json(root / "manifest.json")
    interface = load_yaml(root / "agents/interface.yaml")
    compatibility = interface.get("compatibility", {}) if isinstance(interface, dict) else {}
    intent = manifest.get("intent", {}) if isinstance(manifest.get("intent"), dict) else {}
    risk = manifest.get("risk", {}) if isinstance(manifest.get("risk"), dict) else {}
    permissions = manifest.get("permissions", {}) if isinstance(manifest.get("permissions"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": date.today().isoformat(),
        "package": {
            "name": frontmatter.get("name") or manifest.get("name"),
            "version": manifest.get("version"),
            "owner": manifest.get("owner"),
            "maturity_tier": manifest.get("maturity_tier"),
            "lifecycle_stage": manifest.get("lifecycle_stage"),
            "upstream_inspiration": manifest.get("upstream_inspiration"),
        },
        "intent": {
            "description": frontmatter.get("description", ""),
            "job_to_be_done": intent.get("job_to_be_done", frontmatter.get("description", "")),
            "target_users": intent.get("target_users", []),
            "inputs": intent.get("inputs", []),
            "outputs": intent.get("outputs", []),
            "exclusions": intent.get("exclusions", []),
        },
        "triggers": {
            "should_trigger": trigger_samples(root, "should_trigger"),
            "should_not_trigger": trigger_samples(root, "should_not_trigger"),
            "near_neighbor": trigger_samples(root, "near_neighbor"),
            "adversarial": trigger_samples(root, "adversarial"),
        },
        "workflow": {
            "router_rules": list_items(section_map.get("路由规则", "")),
            "core_workflow": list_items(section_map.get("核心流程", "")),
            "modes_and_gates": list_items(section_map.get("模式与门禁", "")),
            "output_contract": list_items(section_map.get("输出契约", "")),
            "failure_modes": list_items(section_map.get("安全边界", "")),
        },
        "resources": {
            "references": files(root, "references"),
            "scripts": files(root, "scripts"),
            "evals": files(root, "evals"),
            "reports": files(root, "reports"),
            "schemas": files(root, "schemas"),
        },
        "risk": {**risk, "permissions": permissions},
        "governance": {
            "owner": manifest.get("owner"),
            "maturity": manifest.get("maturity_tier"),
            "lifecycle_stage": manifest.get("lifecycle_stage"),
            "review_cadence": manifest.get("review_cadence"),
            "review_due": manifest.get("review_due"),
            "rollback_boundary": "feature branch and immutable semver release; local sync is recoverable",
        },
        "portability": {
            "canonical_format": compatibility.get("canonical_format", "agent-skills"),
            "adapter_targets": compatibility.get("adapter_targets", []),
            "activation": compatibility.get("activation", {}),
            "execution": compatibility.get("execution", {}),
            "trust": compatibility.get("trust", {}),
            "permissions": compatibility.get("permissions", {}),
            "degradation": compatibility.get("degradation", {}),
        },
        "evidence_boundary": {
            "local_validation_is_evidence": True,
            "trigger_fixture_is_evidence": True,
            "provider_or_human_output_evidence": (root / "reports/output-evidence.json").is_file() and load_json(root / "reports/output-evidence.json").get("evidence_kind") in {"provider_backed", "human_blind_review"},
            "missing_external_or_human_evidence_label": "missing evidence",
            "public_claim_policy": "claim only what named package, trigger, runtime, install, provider, or human evidence supports",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the platform-neutral Lvsea Skill IR.")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    root = Path(args.skill_dir).resolve()
    payload = build_ir(root)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
