"""Bench Dev tools: sandboxed source-development surface for Foundry coding agents
(Codex and the agents that will follow it) inside a live bench.

Design goal: "balanced" permissions per Al-Azab's instruction.
- Read/inspect: unrestricted, synchronous, auto-approved.
- Write/build/test/commit: unrestricted, but *only* inside a git worktree that is
  isolated per (bench, app, agent) and checked out on an agent-owned branch
  (agent/<agent-slug>). This lets up to N agents work the same app in parallel
  without touching each other's files or the shared working tree.
- Anything that would touch a protected branch (main/master/production/staging)
  is refused here unconditionally -- there is no code path in this module that
  can write to those branches. The only way "up" from an agent branch is the
  deploy-proposal endpoint, which does not merge anything: it just packages a
  diff + summary for a human to review and merge through the normal git flow.

Every function here is pure Python + subprocess -- no Foundry/Flask coupling --
so it is easy to unit test and easy for a future agent-registration template to
reuse.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
from typing import Any

from agent.app import App

PROTECTED_BRANCHES = {"main", "master", "production", "release", "staging"}
WORKSPACE_DIRNAME = ".agent-workspaces"
MAX_FILE_BYTES = 2_000_000

# Small, explicit allow-list of commands an agent may run inside its own
# workspace. Deliberately not "run arbitrary shell" -- extend this list
# instead of relaxing the check.
ALLOWED_COMMANDS: dict[str, list[str]] = {
    "build": ["bench", "build"],
    "compile": ["python3", "-m", "compileall", "."],
    "lint": ["ruff", "check", "."],
    "test": ["python3", "-m", "pytest", "-q"],
}


class BenchDevError(RuntimeError):
    pass


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    if not slug:
        raise BenchDevError("agent name must contain at least one alphanumeric character")
    return slug


def agent_branch(agent_name: str) -> str:
    return f"agent/{_slug(agent_name)}"


def _workspace_dir(bench, app_name: str, agent_name: str) -> str:
    return os.path.join(bench.directory, WORKSPACE_DIRNAME, _slug(agent_name), _slug(app_name))


def _run(cwd: str, args: list[str], timeout: int = 600) -> dict[str, Any]:
    started = datetime.datetime.now()
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BenchDevError(f"Command timed out after {timeout}s: {' '.join(args)}") from exc
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": " ".join(args),
        "stdout": proc.stdout[-20_000:],
        "stderr": proc.stderr[-20_000:],
        "elapsed_ms": round((datetime.datetime.now() - started).total_seconds() * 1000, 3),
    }


def _safe_join(base: str, relative_path: str) -> str:
    base_real = os.path.realpath(base)
    target_real = os.path.realpath(os.path.join(base_real, relative_path or ""))
    if target_real != base_real and not target_real.startswith(base_real + os.sep):
        raise BenchDevError("path escapes the agent workspace")
    if os.sep + ".git" in target_real.replace(base_real, "", 1):
        raise BenchDevError("the .git directory is not accessible through this API")
    return target_real


def _require_app(bench, app_name: str) -> App:
    try:
        return App(app_name, bench)
    except Exception as exc:
        raise BenchDevError(f"app '{app_name}' does not exist on bench '{bench.name}'") from exc


def _require_workspace(bench, app_name: str, agent_name: str) -> str:
    workspace_dir = _workspace_dir(bench, app_name, agent_name)
    if not os.path.isdir(os.path.join(workspace_dir, ".git")):
        raise BenchDevError(
            f"no workspace for agent '{agent_name}' on app '{app_name}' yet; call ensure_workspace first"
        )
    return workspace_dir


def _current_branch(workspace_dir: str) -> str:
    result = _run(workspace_dir, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if not result["ok"]:
        raise BenchDevError(f"could not resolve current branch: {result['stderr']}")
    return result["stdout"].strip()


def _assert_agent_branch(workspace_dir: str, expected_branch: str) -> None:
    current = _current_branch(workspace_dir)
    if current != expected_branch:
        raise BenchDevError(
            f"workspace is on '{current}', expected agent-owned branch '{expected_branch}'; refusing to act"
        )
    if current in PROTECTED_BRANCHES:
        raise BenchDevError(f"'{current}' is a protected branch; agents may never write to it directly")


# ---------------------------------------------------------------------------
# Read tier -- always auto-approved (GET only)
# ---------------------------------------------------------------------------

def list_agent_workspaces(bench) -> list[dict[str, Any]]:
    root = os.path.join(bench.directory, WORKSPACE_DIRNAME)
    if not os.path.isdir(root):
        return []
    out = []
    for agent_slug in sorted(os.listdir(root)):
        agent_dir = os.path.join(root, agent_slug)
        if not os.path.isdir(agent_dir):
            continue
        for app_slug in sorted(os.listdir(agent_dir)):
            workspace_dir = os.path.join(agent_dir, app_slug)
            if os.path.isdir(os.path.join(workspace_dir, ".git")):
                out.append(
                    {
                        "agent": agent_slug,
                        "app": app_slug,
                        "branch": agent_branch(agent_slug),
                        "path": workspace_dir,
                    }
                )
    return out


def list_tree(bench, app_name: str, agent_name: str, relative_path: str = "") -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    target = _safe_join(workspace_dir, relative_path)
    if not os.path.isdir(target):
        raise BenchDevError("not a directory")
    entries = []
    for entry in sorted(os.listdir(target)):
        if entry == ".git":
            continue
        full = os.path.join(target, entry)
        entries.append({"name": entry, "is_dir": os.path.isdir(full)})
    return {"path": relative_path, "entries": entries}


def read_file(bench, app_name: str, agent_name: str, relative_path: str) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    target = _safe_join(workspace_dir, relative_path)
    if not os.path.isfile(target):
        raise BenchDevError("file not found")
    if os.path.getsize(target) > MAX_FILE_BYTES:
        raise BenchDevError("file too large to read through this API")
    with open(target, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    return {"path": relative_path, "content": content, "bytes": len(content)}


def git_status(bench, app_name: str, agent_name: str) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    return _run(workspace_dir, ["git", "status", "--porcelain=v1", "-b"])


def git_diff(bench, app_name: str, agent_name: str, against: str = "main") -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    against = re.sub(r"[^a-zA-Z0-9/_.-]", "", against or "main") or "main"
    return _run(workspace_dir, ["git", "diff", f"{against}...HEAD"])


# ---------------------------------------------------------------------------
# Confirm tier -- executes immediately, fully audited, scoped to the agent's
# own worktree/branch only.
# ---------------------------------------------------------------------------

def ensure_workspace(bench, app_name: str, agent_name: str) -> dict[str, Any]:
    app = _require_app(bench, app_name)
    branch = agent_branch(agent_name)
    workspace_dir = _workspace_dir(bench, app_name, agent_name)
    if os.path.isdir(os.path.join(workspace_dir, ".git")):
        return {"created": False, "path": workspace_dir, "branch": branch}

    os.makedirs(os.path.dirname(workspace_dir), exist_ok=True)
    branch_list = app.execute("git branch --list " + branch, non_zero_throw=False)["output"]
    if branch not in branch_list:
        app.execute(f"git branch {branch}")
    result = app.execute(f"git worktree add {workspace_dir} {branch}")
    if not result or result.get("status") != "Success":
        raise BenchDevError(f"could not create worktree: {result}")
    return {"created": True, "path": workspace_dir, "branch": branch}


def write_file(bench, app_name: str, agent_name: str, relative_path: str, content: str) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    _assert_agent_branch(workspace_dir, agent_branch(agent_name))
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise BenchDevError("content too large to write through this API")
    target = _safe_join(workspace_dir, relative_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(content)
    return {"path": relative_path, "bytes_written": len(content.encode("utf-8"))}


def run_allowed_command(bench, app_name: str, agent_name: str, command_key: str) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    _assert_agent_branch(workspace_dir, agent_branch(agent_name))
    args = ALLOWED_COMMANDS.get(str(command_key or "").strip().lower())
    if args is None:
        raise BenchDevError(f"'{command_key}' is not an allowed command; allowed: {sorted(ALLOWED_COMMANDS)}")
    return _run(workspace_dir, args)


def commit(bench, app_name: str, agent_name: str, message: str) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    branch = agent_branch(agent_name)
    _assert_agent_branch(workspace_dir, branch)
    message = str(message or "").strip()
    if not message:
        raise BenchDevError("commit message is required")
    add_result = _run(workspace_dir, ["git", "add", "-A"])
    if not add_result["ok"]:
        raise BenchDevError(f"git add failed: {add_result['stderr']}")
    commit_result = _run(workspace_dir, ["git", "commit", "-m", message])
    return {"branch": branch, "add": add_result, "commit": commit_result}


# ---------------------------------------------------------------------------
# Manual-approval tier -- the *only* bridge from an agent branch back toward
# a protected branch, and it never merges anything itself. It packages the
# diff/summary that a human reviews and merges by hand through the normal
# git remote / PR flow. Name deliberately contains "deploy" so the existing
# production-tools risk classifier (`_route_risk`) auto-tags this route
# high-risk / manual-approval without any special-casing needed there.
# ---------------------------------------------------------------------------

def build_deploy_proposal(
    bench, app_name: str, agent_name: str, title: str, summary: str, against: str = "main"
) -> dict[str, Any]:
    workspace_dir = _require_workspace(bench, app_name, agent_name)
    branch = agent_branch(agent_name)
    diff = git_diff(bench, app_name, agent_name, against=against)
    stat = _run(workspace_dir, ["git", "diff", "--stat", f"{against}...HEAD"])
    return {
        "title": str(title or "").strip() or f"{agent_name}: changes to {app_name}",
        "summary": str(summary or "").strip(),
        "branch": branch,
        "against": against,
        "stat": stat.get("stdout"),
        "diff_preview": (diff.get("stdout") or "")[:20_000],
        "note": (
            "This proposal does not modify any branch. A human must review the diff "
            "and merge it through the normal git remote / pull-request flow."
        ),
    }
