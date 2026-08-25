#!/usr/bin/env python3
"""Build a deterministic lvsea-daihuo route preview without calling providers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


PLATFORMS = {"douyin", "kuaishou", "xiaohongshu", "tiktok", "reels", "shorts", "shipinhao"}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def build_plan(request: dict[str, Any]) -> dict[str, Any]:
    product = request.get("product") if isinstance(request.get("product"), dict) else {}
    goal = request.get("goal") if isinstance(request.get("goal"), dict) else {}
    permissions = request.get("permissions") if isinstance(request.get("permissions"), dict) else {}
    assets = product.get("assets") if isinstance(product.get("assets"), list) else []
    references = request.get("references") if isinstance(request.get("references"), list) else []
    mode = str(request.get("mode") or "preview").lower()
    errors: list[str] = []
    missing: list[str] = []

    if not str(product.get("name") or "").strip():
        errors.append("product.name is required")
    facts = product.get("facts")
    if not isinstance(facts, list) or not facts:
        errors.append("product.facts must contain at least one source-backed or user-asserted fact")
    platform = str(goal.get("platform") or "").lower()
    if platform not in PLATFORMS:
        errors.append("goal.platform must be one of the supported platform values")
    duration = goal.get("duration_sec")
    if not isinstance(duration, (int, float)) or not 5 <= float(duration) <= 180:
        errors.append("goal.duration_sec must be between 5 and 180")
    if str(goal.get("aspect_ratio") or "9:16") not in {"9:16", "16:9", "1:1"}:
        errors.append("goal.aspect_ratio must be 9:16, 16:9, or 1:1")
    if not assets:
        missing.append("product.assets")
    if not references:
        missing.append("references")
    if not os.environ.get("CLIPCAT_API_KEY"):
        missing.append("CLIPCAT_API_KEY")
    if not permissions.get("allow_paid", False):
        missing.append("paid_confirmation")
    if not request.get("talking_head_video"):
        missing.append("talking_head_video")

    routes: list[dict[str, Any]] = []
    routes.append({
        "capability": "ecom-details-image",
        "purpose": "product_visual_plan",
        "status": "ready" if assets else "prompt_only",
        "action": "create product hero, detail, scene, and UGC prompts; call image API only when configured",
    })
    routes.append({
        "capability": "clipcat",
        "purpose": "viral_research",
        "status": "ready" if os.environ.get("CLIPCAT_API_KEY") or references else "missing_evidence",
        "action": "search or analyze references; quote before any paid video task",
    })
    routes.append({
        "capability": "clipforge-video",
        "purpose": "local_render",
        "status": "planned",
        "action": "import/product/create, compose asynchronously, gate, contact sheet, qc",
    })
    if request.get("talking_head_video"):
        routes.append({
            "capability": "chengfeng-videocut",
            "purpose": "talking_head_refinement",
            "status": "planned",
            "action": "cut review, subtitle, visual, export",
        })

    final_status = "blocked" if errors else ("preview" if mode == "preview" else "provider_pending")
    return {
        "skill": "lvsea-daihuo",
        "mode": mode,
        "status": final_status,
        "errors": errors,
        "missing_evidence": missing,
        "routes": routes,
        "paid_call_allowed": bool(mode == "paid" and permissions.get("allow_paid") is True),
        "publish_allowed": False,
        "next_action": "fix errors" if errors else "run provider-specific preflight and retain the evidence ledger",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview an lvsea-daihuo route without provider calls.")
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args()
    result = build_plan(load_json(args.request))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(2 if result["errors"] else 0)


if __name__ == "__main__":
    main()
