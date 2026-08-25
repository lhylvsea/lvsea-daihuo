#!/usr/bin/env python3
"""Publish a Lvsea Skill through a feature branch, PR, Release, and clean install."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from release_check import evaluate, scan_secrets
from runtime import run
from validate_skill import load_json, parse_frontmatter, validate


class PublishError(RuntimeError):
    pass


def configure_console() -> None:
    """Keep structured results printable on Windows consoles using legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def checked(args: list[str], cwd: Path, *, timeout: float = 300.0) -> dict[str, Any]:
    result = run(args, cwd, timeout=timeout)
    if not result["ok"]:
        detail = result["stderr"] or result["stdout"] or "unknown error"
        raise PublishError(f"command failed: {' '.join(args)}\n{detail}")
    return result


def identity(root: Path) -> dict[str, str]:
    frontmatter = parse_frontmatter((root / "SKILL.md").read_text(encoding="utf-8"))
    manifest = load_json(root / "manifest.json")
    name = str(frontmatter.get("name", "")).strip()
    description = " ".join(str(frontmatter.get("description", "")).split())
    version = str(manifest.get("version", "")).strip()
    owner = str(manifest.get("owner", "")).strip()
    if not name or not description:
        raise PublishError("SKILL.md frontmatter requires name and description")
    if manifest.get("name") != name:
        raise PublishError("manifest.json name does not match SKILL.md")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise PublishError("manifest.json version must be semantic X.Y.Z")
    if not owner:
        raise PublishError("manifest.json owner is required")
    return {"name": name, "description": description, "version": version, "owner": owner}


def parse_origin(url: str) -> tuple[str | None, str | None]:
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", url.strip())
    return (match.group(1), match.group(2)) if match else (None, None)


def origin_identity(root: Path) -> tuple[str | None, str | None]:
    result = run(["git", "remote", "get-url", "origin"], root)
    return parse_origin(result["stdout"]) if result["ok"] else (None, None)


def check_prerequisites(root: Path) -> None:
    for command in (["git", "--version"], ["gh", "--version"], ["npx", "--version"], ["python", "--version"]):
        checked(command, root)
    checked(["gh", "auth", "status"], root)


def github_user(root: Path, explicit: str | None, origin_owner: str | None) -> str:
    if explicit:
        return explicit
    if origin_owner:
        return origin_owner
    result = checked(["gh", "api", "user", "--jq", ".login"], root)
    if not result["stdout"]:
        raise PublishError("unable to resolve GitHub user")
    return result["stdout"].strip()


def ensure_license(root: Path, owner: str, *, write: bool) -> list[str]:
    path = root / "LICENSE"
    if path.exists():
        return []
    if not write:
        return ["LICENSE"]
    year = dt.datetime.now().year
    path.write_text(
        f"""MIT License

Copyright (c) {year} {owner}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""",
        encoding="utf-8",
    )
    return ["LICENSE"]


def readme_failures(root: Path) -> list[str]:
    path = root / "README.md"
    if not path.is_file():
        return ["README.md missing"]
    text = path.read_text(encoding="utf-8")
    requirements = {
        "install command": "npx skills add" in text,
        "natural-language examples": "你可以这样说" in text,
        "verification command": "validate_skill.py" in text,
        "prerequisite checklist": "- [ ]" in text,
        "troubleshooting": "Troubleshooting" in text,
        "license": "## License" in text or "## 许可证" in text,
        "qiaomu upstream credit": "qiaomu-meta-skill" in text,
        "yao upstream credit": "yao-meta-skill" in text,
    }
    return [f"README missing {label}" for label, passed in requirements.items() if not passed]


def prepare_package(root: Path, owner: str, *, write: bool) -> dict[str, Any]:
    changes = ensure_license(root, owner, write=write)
    failures = readme_failures(root)
    return {"changes": changes, "failures": failures}


def repo_exists(root: Path, slug: str) -> bool:
    return run(["gh", "repo", "view", slug, "--json", "url"], root)["ok"]


def release_exists(root: Path, slug: str, version: str) -> bool:
    return run(["gh", "release", "view", f"v{version}", "--repo", slug], root)["ok"]


def default_branch(root: Path, slug: str) -> str:
    result = run(["gh", "repo", "view", slug, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"], root)
    return result["stdout"].strip() if result["ok"] and result["stdout"].strip() else "main"


def branch_slug(name: str, version: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return f"codex/publish-{safe}-v{version.replace('.', '-')}"


def assert_feature_branch(branch: str, default: str) -> None:
    if not branch or branch in {"main", "master", default} or not branch.startswith("codex/"):
        raise PublishError(f"refusing publication branch: {branch or '<detached>'}")


def copy_package(source: Path, destination: Path) -> None:
    ignore = shutil.ignore_patterns(".git", ".DS_Store", "__pycache__", "*.pyc", "*.pyo", ".agents", ".codex")
    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)


def configure_git_identity(root: Path, github_login: str) -> None:
    """Set commit identity only inside the temporary publication clone."""
    checked(["git", "config", "user.name", github_login], root)
    checked(["git", "config", "user.email", f"{github_login}@users.noreply.github.com"], root)


def staged_changes(root: Path) -> bool:
    return not run(["git", "diff", "--cached", "--quiet"], root)["ok"]


def pr_is_mergeable(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if payload.get("mergeable") != "MERGEABLE":
        blockers.append(f"PR mergeability is not ready: {payload.get('mergeable') or 'unknown'}")
    if payload.get("reviewDecision") == "CHANGES_REQUESTED":
        blockers.append("PR has requested changes")
    for review in payload.get("reviews") or []:
        if review.get("state") == "CHANGES_REQUESTED":
            blockers.append("a PR review requested changes")
    for check in payload.get("statusCheckRollup") or []:
        if check.get("conclusion") in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
            blockers.append(f"check failed: {check.get('name', 'unknown')}")
        elif check.get("status") and check.get("status") != "COMPLETED":
            blockers.append(f"check still pending: {check.get('name', 'unknown')}")
    return not blockers, blockers


def pr_payload(root: Path, url: str) -> dict[str, Any]:
    for _ in range(6):
        result = run(["gh", "pr", "view", url, "--json", "url,state,mergeable,reviewDecision,statusCheckRollup,comments,reviews"], root)
        if result["ok"]:
            payload = json.loads(result["stdout"])
            ready, blockers = pr_is_mergeable(payload)
            if ready or payload.get("mergeable") != "UNKNOWN":
                return payload
        time.sleep(2)
    raise PublishError("unable to obtain a mergeable PR state")


def verify_discovery(root: Path, slug: str, skill_name: str) -> dict[str, Any]:
    result = run(["npx", "--yes", "skills", "add", slug, "--list"], root, timeout=300)
    output = f"{result['stdout']}\n{result['stderr']}"
    found = skill_name in output and "No valid skills found" not in output
    return {"ok": result["ok"] and found, "returncode": result["returncode"], "skill": skill_name, "found": found, "output_tail": output[-2000:]}


def sync_local(source: Path, skill_name: str) -> dict[str, Any]:
    target = Path.home() / ".agents" / "skills" / skill_name
    if target.resolve() == source.resolve():
        return {"status": "skipped", "target": str(target), "reason": "source is already canonical"}
    staging = target.parent / f".{skill_name}.incoming"
    backup_root = Path.home() / ".agents" / "skill-backups"
    if staging.exists():
        raise PublishError(f"stale local sync staging path exists: {staging}")
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_package(source, staging)
    backup = None
    if target.exists() or target.is_symlink():
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{skill_name}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        target.rename(backup)
    staging.rename(target)
    return {"status": "updated" if backup else "created", "target": str(target), "backup": str(backup) if backup else None}


def publish(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.skill_dir).expanduser().resolve()
    if not source.is_dir():
        raise PublishError(f"skill directory does not exist: {source}")
    meta = identity(source)
    check_prerequisites(source)
    origin_owner, origin_repo = origin_identity(source)
    owner = github_user(source, args.github_user, origin_owner)
    repo = args.repo_name or origin_repo or meta["name"]
    slug = f"{owner}/{repo}"
    prepared = prepare_package(source, meta["owner"], write=not args.dry_run)
    if args.dry_run:
        return {"ok": not prepared["failures"], "mode": "dry-run", "skill": meta, "repository": slug, "repository_exists": repo_exists(source, slug), "would_change": prepared["changes"], "failures": prepared["failures"], "default_branch_push": "forbidden"}
    if prepared["failures"]:
        raise PublishError("README preparation failed: " + "; ".join(prepared["failures"]))
    package = validate(source)
    if not package["ok"]:
        raise PublishError(f"package validation failed: {package}")
    if args.prepare_only:
        return {"ok": True, "mode": "prepare-only", "skill": meta, "repository": slug, "changes": prepared["changes"]}

    exists = repo_exists(source, slug)
    if exists and release_exists(source, slug, meta["version"]):
        if not args.verify_only:
            raise PublishError(f"release v{meta['version']} already exists; bump manifest.json before publishing")
        discovery = verify_discovery(source, slug, meta["name"])
        published = evaluate(source, "published", run_tests=True, install_check=True)
        return {"ok": discovery["ok"] and published["ok"], "mode": "verify-only", "repository": slug, "discovery": discovery, "release": published}
    if args.verify_only:
        raise PublishError("--verify-only requires an existing versioned release")

    if not exists:
        visibility = "--private" if args.private else "--public"
        checked(["gh", "repo", "create", slug, visibility, "--add-readme", "--description", meta["description"][:300]], source)

    temporary = tempfile.TemporaryDirectory(prefix="lvsea-skill-publish-")
    workspace = Path(temporary.name) / repo
    try:
        checked(["git", "clone", f"https://github.com/{slug}.git", str(workspace)], source)
        configure_git_identity(workspace, owner)
        copy_package(source, workspace)
        default = default_branch(workspace, slug)
        branch = args.branch or branch_slug(meta["name"], meta["version"])
        checked(["git", "switch", "-c", branch], workspace)
        assert_feature_branch(branch, default)

        local_gates = evaluate(workspace, "local", run_tests=True, install_check=False)
        if not local_gates["ok"]:
            raise PublishError(f"local release gates blocked: {local_gates['summary']}")
        secrets = scan_secrets(workspace)
        if secrets:
            raise PublishError(f"secret scan blocked publication: {secrets}")
        checked(["git", "add", "-A"], workspace)
        checked(["git", "diff", "--cached", "--check"], workspace)
        if staged_changes(workspace):
            checked(["git", "commit", "-m", f"release: prepare {meta['name']} v{meta['version']}"], workspace)
        checked(["git", "push", "-u", "origin", branch], workspace)

        existing = run(["gh", "pr", "list", "--repo", slug, "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url"], workspace)
        pr_url = existing["stdout"].strip() if existing["ok"] else ""
        if not pr_url:
            body = (
                f"Publish `{meta['name']}` v{meta['version']} through the Lvsea governed release flow.\n\n"
                "- intent, trigger regression, context budget and trust gates run locally\n"
                "- no direct default-branch push\n"
                "- merge is followed by a versioned Release and clean installation check"
            )
            created = checked(["gh", "pr", "create", "--repo", slug, "--base", default, "--head", branch, "--title", f"release: {meta['name']} v{meta['version']}", "--body", body], workspace)
            pr_url = created["stdout"].splitlines()[-1].strip()
        pr_gates = evaluate(workspace, "pr", run_tests=True, install_check=False)
        if not pr_gates["ok"]:
            raise PublishError(f"PR release gates blocked: {pr_gates['summary']}")
        payload = pr_payload(workspace, pr_url)
        ready, blockers = pr_is_mergeable(payload)
        if not ready:
            raise PublishError("PR is not ready to merge: " + "; ".join(blockers))
        if args.no_merge:
            return {"ok": True, "mode": "pr-ready", "repository": slug, "branch": branch, "pull_request": pr_url, "local_gates": local_gates["summary"], "pr_gates": pr_gates["summary"]}

        checked(["gh", "pr", "merge", pr_url, "--repo", slug, "--squash", "--delete-branch", "--subject", f"release: {meta['name']} v{meta['version']}"], workspace)
        checked(["git", "fetch", "origin", default], workspace)
        checked(["git", "switch", default], workspace)
        checked(["git", "pull", "--ff-only", "origin", default], workspace)
        checked(["gh", "release", "create", f"v{meta['version']}", "--repo", slug, "--target", default, "--title", f"v{meta['version']}", "--generate-notes"], workspace)
        discovery = verify_discovery(workspace, slug, meta["name"])
        if not discovery["ok"]:
            raise PublishError(f"npx skill discovery failed: {discovery}")
        published = evaluate(workspace, "published", run_tests=True, install_check=True)
        if not published["ok"]:
            raise PublishError(f"published release gates blocked: {published['summary']}")
        sync = {"status": "skipped"} if args.no_sync_local else sync_local(source, meta["name"])
        return {"ok": True, "mode": "published", "repository": f"https://github.com/{slug}", "release": f"https://github.com/{slug}/releases/tag/v{meta['version']}", "install": f"npx skills add {slug}", "pull_request": pr_url, "discovery": discovery, "published_gates": published["summary"], "sync": sync, "direct_default_branch_push": False}
    finally:
        temporary.cleanup()


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="Publish a Lvsea Skill through branch, PR, Release, and install gates.")
    parser.add_argument("skill_dir")
    parser.add_argument("--github-user")
    parser.add_argument("--repo-name")
    parser.add_argument("--branch")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--no-sync-local", action="store_true")
    args = parser.parse_args()
    try:
        result = publish(args)
    except (PublishError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
