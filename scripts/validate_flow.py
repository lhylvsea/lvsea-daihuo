#!/usr/bin/env python3
"""Validate the public input and artifact contracts for lvsea-daihuo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STATUS = {"preview", "ready", "blocked", "missing_evidence", "provider_pending"}
ALLOWED_FACT_STATUS = {"verified", "user_asserted", "unverified", "rejected"}


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def validate_request(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    product = payload.get("product")
    goal = payload.get("goal")
    if not isinstance(product, dict) or not product.get("name"):
        errors.append("product.name is required")
    if not isinstance(product, dict) or not isinstance(product.get("facts"), list) or not product["facts"]:
        errors.append("product.facts must be a non-empty list")
    if isinstance(product, dict):
        for index, fact in enumerate(product.get("facts", [])):
            if not isinstance(fact, dict):
                errors.append(f"product.facts[{index}] must be an object")
                continue
            if fact.get("status", "user_asserted") not in ALLOWED_FACT_STATUS:
                errors.append(f"product.facts[{index}].status is invalid")
    if not isinstance(goal, dict):
        errors.append("goal must be an object")
    else:
        if goal.get("platform") not in {"douyin", "kuaishou", "xiaohongshu", "tiktok", "reels", "shorts", "shipinhao"}:
            errors.append("goal.platform is invalid")
        if not isinstance(goal.get("duration_sec"), (int, float)):
            errors.append("goal.duration_sec must be numeric")
    return errors


def validate_artifact_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = payload.get("status")
    if status not in ALLOWED_STATUS:
        errors.append("manifest.status is invalid")
    if not payload.get("skill") == "lvsea-daihuo":
        errors.append("manifest.skill must be lvsea-daihuo")
    if not isinstance(payload.get("missing_evidence", []), list):
        errors.append("manifest.missing_evidence must be a list")
    if status == "ready":
        if not payload.get("final_video"):
            errors.append("ready manifest requires final_video")
        if payload.get("gate_status") not in {"pass", "pass_with_reviewed_warn"}:
            errors.append("ready manifest requires a passing gate_status")
        if payload.get("human_reviewed") is not True:
            errors.append("ready manifest requires human_reviewed=true")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate lvsea-daihuo request or artifact JSON.")
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--kind", choices=("request", "manifest"), default="request")
    args = parser.parse_args()
    payload = load(args.json_file)
    errors = validate_request(payload) if args.kind == "request" else validate_artifact_manifest(payload)
    result = {"ok": not errors, "kind": args.kind, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
