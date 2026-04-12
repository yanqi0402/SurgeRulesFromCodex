#!/usr/bin/env python3
"""Refresh Surge rule outputs and safely commit publishable list changes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SUBREPO = Path(__file__).resolve().parents[1]
ROOT = SUBREPO.parent
ROOT_UPDATER = ROOT / "scripts" / "update_claude_code_rules.py"
SUBREPO_UPDATER = SUBREPO / "scripts" / "update_ai_rules.py"
PUBLISHABLE_FILES = (
    "AI.list",
    "apple.list",
    "jd.list",
    "netflix.list",
    "hbo_max.list",
    "tik_tok.list",
    "microsoft.list",
)
COMMIT_MESSAGE = "chore: update rule lists"
COMMIT_AUTHOR_NAME = "Codex Automation"
COMMIT_AUTHOR_EMAIL = "automation@local.invalid"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def tracked_paths(repo: Path) -> list[str]:
    result = run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def main() -> int:
    summary: dict[str, object] = {
        "root_updater": str(ROOT_UPDATER),
        "subrepo_updater": str(SUBREPO_UPDATER),
        "subrepo": str(SUBREPO),
        "publishable_files": list(PUBLISHABLE_FILES),
        "tracked_dirty_before": False,
        "tracked_dirty_paths_before": [],
        "changed_publishable_files": [],
        "unexpected_tracked_changes": [],
        "commit_created": False,
        "commit_sha": None,
    }

    before_paths = tracked_paths(SUBREPO)
    summary["tracked_dirty_before"] = bool(before_paths)
    summary["tracked_dirty_paths_before"] = before_paths

    print(f"[run] {ROOT_UPDATER.relative_to(ROOT)}")
    root_result = run([sys.executable, str(ROOT_UPDATER)], cwd=ROOT)
    if root_result.stdout:
        print(root_result.stdout, end="")
    if root_result.stderr:
        print(root_result.stderr, end="", file=sys.stderr)

    print(f"[run] {SUBREPO_UPDATER.relative_to(SUBREPO)}")
    subrepo_result = run([sys.executable, str(SUBREPO_UPDATER)], cwd=SUBREPO)
    if subrepo_result.stdout:
        print(subrepo_result.stdout, end="")
    if subrepo_result.stderr:
        print(subrepo_result.stderr, end="", file=sys.stderr)

    after_paths = tracked_paths(SUBREPO)
    changed_publishable = [path for path in after_paths if path in PUBLISHABLE_FILES]
    unexpected_paths = [path for path in after_paths if path not in PUBLISHABLE_FILES]
    summary["changed_publishable_files"] = changed_publishable
    summary["unexpected_tracked_changes"] = unexpected_paths

    if before_paths:
        print(
            "[skip] Subrepo has tracked changes before automation run; "
            "skipping commit to avoid publishing unrelated edits.",
            file=sys.stderr,
        )
    elif unexpected_paths:
        print(
            "[skip] Unexpected tracked changes detected after regeneration; "
            "skipping commit to avoid publishing unrelated edits.",
            file=sys.stderr,
        )
    elif changed_publishable:
        run(["git", "add", "--", *PUBLISHABLE_FILES], cwd=SUBREPO)
        run(
            [
                "git",
                "-c",
                f"user.name={COMMIT_AUTHOR_NAME}",
                "-c",
                f"user.email={COMMIT_AUTHOR_EMAIL}",
                "commit",
                "-m",
                COMMIT_MESSAGE,
            ],
            cwd=SUBREPO,
        )
        commit_sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=SUBREPO).stdout.strip()
        summary["commit_created"] = True
        summary["commit_sha"] = commit_sha
        print(f"[commit] Created {commit_sha} with message: {COMMIT_MESSAGE}")
    else:
        print("[ok] No publishable rule changes detected.")

    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
