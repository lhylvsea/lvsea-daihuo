#!/usr/bin/env python3
"""Run local, PR, or published release gates for a Lvsea Skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from context_sizer import measure
from runtime import run
from validate_skill import load_json, validate

SECRET_PATTERNS = {
    "OpenAI-like key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "assigned credential": re.compile(r'''(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*["'][^"']{8,}["']'''),
}
SCAN_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".sh", ".toml"}
IGNORED_PARTS = {".git", "__pycache__", "node_modules", "dist", ".agents", ".codex"}


def gate(gates: list[dict[str, Any]], name: str, status: str, evidence: Any) -> None:
    gates.append({"gate": name, "status": status, "evidence": evidence})


def scan_secrets(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append({"file": relative.as_posix(), "line": line_number, "kind": label})
    return findings


def repo_slug(root: Path) -> str | None:
    result = run(["git", "remote", "get-url", "origin"], root)
    if not result["ok"]:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$", result["stdout"])
    return match.group(1) if match else None


def version_consistency(root: Path) -> dict[str, Any]:
    manifest = load_json(root / "manifest.json")
    name = str(manifest.get("name", ""))
    version = str(manifest.get("version", ""))
    failures: list[str] = []
    ir = load_json(root / "reports/skill-ir.json") if (root / "reports/skill-ir.json").is_file() else {}
    package = ir.get("package", {})
    if package.get("name") != name:
        failures.append("Skill IR package name does not match manifest")
    if package.get("version") != version:
        failures.append("Skill IR package version does not match manifest")
    trigger = load_json(root / "reports/trigger-eval.json") if (root / "reports/trigger-eval.json").is_file() else {}
    if trigger.get("ok") is not True:
        failures.append("trigger evaluation is not passing")
    return {"ok": not failures, "failures": failures, "manifest_name": name, "manifest_version": version}


def output_evidence_status(root: Path) -> tuple[str, dict[str, Any]]:
    path = root / "reports/output-evidence.json"
    if not path.is_file():
        return "warn", {"path": "reports/output-evidence.json", "missing_evidence": True}
    try:
        payload = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return "block", {"path": "reports/output-evidence.json", "error": str(exc)}
    kind = payload.get("evidence_kind")
    if kind in {"provider_backed", "human_blind_review"} and payload.get("ok") is True:
        return "pass", {"path": "reports/output-evidence.json", "evidence_kind": kind, "ok": True}
    return "warn", {
        "path": "reports/output-evidence.json",
        "evidence_kind": kind,
        "ok": payload.get("ok"),
        "missing_evidence": "static fixtures/specifications do not prove provider or human output quality",
    }


def evaluate(root: Path, phase: str, run_tests: bool, install_check: bool) -> dict[str, Any]:
    root = root.resolve()
    gates: list[dict[str, Any]] = []
    package = validate(root)
    package_status = "block" if not package["ok"] else ("warn" if package["warnings"] else "pass")
    gate(gates, "package_validation", package_status, package)

    context = measure(root)
    gate(gates, "context_budget", "block" if context["status"] == "block" else context["status"], context)

    consistency = version_consistency(root)
    gate(gates, "version_and_report_consistency", "pass" if consistency["ok"] else "block", consistency)

    secrets = scan_secrets(root)
    gate(gates, "secret_scan", "pass" if not secrets else "block", {"findings": secrets})

    diff_check = run(["git", "diff", "--check"], root)
    gate(gates, "git_diff_check", "pass" if diff_check["ok"] else "block", diff_check)

    branch_result = run(["git", "branch", "--show-current"], root)
    branch = branch_result["stdout"] if branch_result["ok"] else ""
    branch_status = "block" if not branch or (phase in {"local", "pr"} and branch in {"main", "master"}) else "pass"
    gate(gates, "feature_branch", branch_status, {"branch": branch})

    status_result = run(["git", "status", "--porcelain"], root)
    dirty = bool(status_result["stdout"]) if status_result["ok"] else True
    dirty_status = "warn" if phase == "local" and dirty else ("block" if dirty else "pass")
    gate(gates, "clean_worktree", dirty_status, {"dirty": dirty})

    if run_tests:
        tests = run(["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], root, timeout=300)
        gate(gates, "unit_tests", "pass" if tests["ok"] else "block", tests)
    else:
        gate(gates, "unit_tests", "warn", {"missing_evidence": "rerun with --run-tests"})

    slug = repo_slug(root)
    manifest = load_json(root / "manifest.json")
    version = str(manifest.get("version", ""))
    name = str(manifest.get("name", ""))

    if phase == "pr":
        remote_branch = run(["git", "ls-remote", "--heads", "origin", branch], root) if slug and branch else {"ok": False, "stdout": ""}
        gate(gates, "remote_branch", "pass" if remote_branch["ok"] and remote_branch["stdout"] else "block", {"repo": slug, "branch": branch})
        pr = run(["gh", "pr", "list", "--repo", slug or "", "--head", branch, "--state", "open", "--json", "url,state"], root) if slug and branch else {"ok": False, "stdout": "", "stderr": "missing repo or branch"}
        try:
            rows = json.loads(pr["stdout"] or "[]") if pr["ok"] else []
        except json.JSONDecodeError:
            rows = []
        gate(gates, "open_pr", "pass" if rows else "block", {"pull_requests": rows, "error": pr.get("stderr", "")})

    if phase == "published":
        if slug:
            default_result = run(["gh", "repo", "view", slug, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"], root)
            default_branch = default_result["stdout"] or "main"
            remote = run(["gh", "api", f"repos/{slug}/contents/manifest.json?ref={default_branch}", "-H", "Accept: application/vnd.github.raw+json"], root)
            try:
                remote_version = json.loads(remote["stdout"]).get("version") if remote["ok"] else None
            except json.JSONDecodeError:
                remote_version = None
            gate(gates, "remote_default_version", "pass" if remote_version == version else "block", {"repo": slug, "default_branch": default_branch, "local_version": version, "remote_version": remote_version})
            release = run(["gh", "release", "view", f"v{version}", "--repo", slug, "--json", "url,tagName,isDraft"], root)
            gate(gates, "github_release", "pass" if release["ok"] else "block", release)
        else:
            gate(gates, "remote_default_version", "block", {"repo": None})
            gate(gates, "github_release", "block", {"repo": None})

    if install_check and slug:
        with tempfile.TemporaryDirectory(prefix="lvsea-clean-install-") as directory:
            isolated = Path(directory)
            env = dict(os.environ)
            env["HOME"] = str(isolated)
            env["USERPROFILE"] = str(isolated)
            install = run(["npx", "--yes", "skills", "add", slug, "--skill", name, "--yes"], isolated, timeout=300, env=env)
            candidates = [isolated / ".agents/skills" / name / "SKILL.md", isolated / ".codex/skills" / name / "SKILL.md"]
            entrypoint = next((path for path in candidates if path.is_file()), candidates[0])
            evidence = {**install, "installed_entrypoint": str(entrypoint), "entrypoint_exists": entrypoint.is_file()}
            gate(gates, "clean_install", "pass" if install["ok"] and entrypoint.is_file() else "block", evidence)
    else:
        gate(gates, "clean_install", "warn", {"missing_evidence": "rerun with --install-check after the target revision is remote"})

    output_status, output_evidence = output_evidence_status(root)
    gate(gates, "provider_or_human_output_evidence", output_status, output_evidence)

    blocks = [item for item in gates if item["status"] == "block"]
    warnings = [item for item in gates if item["status"] == "warn"]
    return {
        "ok": not blocks,
        "phase": phase,
        "root": root.name,
        "version": version,
        "repository": slug,
        "summary": {"pass": len(gates) - len(blocks) - len(warnings), "warn": len(warnings), "block": len(blocks)},
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Lvsea Skill release readiness.")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--phase", choices=("local", "pr", "published"), default="local")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--install-check", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate(Path(args.skill_dir), args.phase, args.run_tests, args.install_check)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = Path(args.skill_dir).resolve() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
