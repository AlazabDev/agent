"""HTTP surface for agent.bench_dev.

Deliberately its own blueprint with a plain (non-/ai/) prefix so that
`/ai/api/production-tools/discover` picks these routes up like any other
Agent capability -- that discovery step explicitly skips everything under
/ai/, since /ai/ is the control plane, not a bindable tool surface.

Route naming matters for automatic risk classification in
agent/ai_control/routes.py:_route_risk(): GET routes are always "read/auto".
Mutating routes are "high/manual" only if the path contains a marker like
"deploy"/"database"/"restart"/etc. Every write/build/commit route below is
scoped to an agent's own isolated git worktree and branch (never a protected
branch), so "review/confirm" (auto-execute + audited) is the correct default
for them. Only the deploy-proposal route intentionally matches the "deploy"
marker so it always requires a human decision in /ai/api/approvals.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from agent.ai_control import bench_dev as dev
from agent.ai_control.bench_dev import BenchDevError
from agent.exceptions import BenchNotExistsException
from agent.server import Server

bench_dev_bp = Blueprint("bench_dev", __name__, url_prefix="/bench-dev")


def _bench(bench_name: str):
    try:
        return Server().get_bench(bench_name)
    except BenchNotExistsException as exc:
        raise BenchDevError(f"bench '{bench_name}' does not exist") from exc


def _handle(fn):
    try:
        return jsonify(fn()), 200
    except BenchDevError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "type": type(exc).__name__}), 500


# --- read tier ---------------------------------------------------------

@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/tree")
def tree(bench_name, app_name, agent_name):
    path = request.args.get("path", "")
    return _handle(lambda: dev.list_tree(_bench(bench_name), app_name, agent_name, path))


@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/file")
def file(bench_name, app_name, agent_name):
    path = request.args.get("path")
    if not path:
        return jsonify({"ok": False, "error": "path query parameter is required"}), 400
    return _handle(lambda: dev.read_file(_bench(bench_name), app_name, agent_name, path))


@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/git/status")
def status(bench_name, app_name, agent_name):
    return _handle(lambda: dev.git_status(_bench(bench_name), app_name, agent_name))


@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/git/diff")
def diff(bench_name, app_name, agent_name):
    against = request.args.get("against", "main")
    return _handle(lambda: dev.git_diff(_bench(bench_name), app_name, agent_name, against))


@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/workspaces")
def workspaces(bench_name, app_name, agent_name):
    return _handle(lambda: {"workspaces": dev.list_agent_workspaces(_bench(bench_name))})


# --- confirm tier (auto-execute, fully audited, agent's own branch only) --

@bench_dev_bp.route(
    "/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/workspace", methods=["POST"]
)
def ensure_workspace(bench_name, app_name, agent_name):
    return _handle(lambda: dev.ensure_workspace(_bench(bench_name), app_name, agent_name))


@bench_dev_bp.route(
    "/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/write", methods=["POST"]
)
def write(bench_name, app_name, agent_name):
    payload = request.get_json(force=True) or {}
    path = payload.get("path")
    content = payload.get("content")
    if not path or content is None:
        return jsonify({"ok": False, "error": "path and content are required"}), 400
    return _handle(lambda: dev.write_file(_bench(bench_name), app_name, agent_name, path, content))


@bench_dev_bp.route("/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/run", methods=["POST"])
def run(bench_name, app_name, agent_name):
    payload = request.get_json(force=True) or {}
    command = payload.get("command")
    if not command:
        return jsonify({"ok": False, "error": "command is required"}), 400
    return _handle(lambda: dev.run_allowed_command(_bench(bench_name), app_name, agent_name, command))


@bench_dev_bp.route(
    "/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/commit", methods=["POST"]
)
def commit(bench_name, app_name, agent_name):
    payload = request.get_json(force=True) or {}
    message = payload.get("message")
    return _handle(lambda: dev.commit(_bench(bench_name), app_name, agent_name, message))


# --- manual-approval tier (route name contains "deploy" on purpose) -------

@bench_dev_bp.route(
    "/<string:bench_name>/<string:app_name>/agents/<string:agent_name>/deploy-proposal", methods=["POST"]
)
def deploy_proposal(bench_name, app_name, agent_name):
    payload = request.get_json(force=True) or {}
    return _handle(
        lambda: dev.build_deploy_proposal(
            _bench(bench_name),
            app_name,
            agent_name,
            payload.get("title"),
            payload.get("summary"),
            payload.get("against", "main"),
        )
    )
