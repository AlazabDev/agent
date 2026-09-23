#!/usr/bin/env python3
"""Unified onboarding for a Foundry agent (Codex, and the 11 agents that follow it)
into this Agent's AI Control Center: Foundry sync -> A2A participant -> tool bindings
-> per-app bench-dev workspace.

This is the *one* script every future agent goes through. To onboard a new agent:
  1. Create it in the Azure AI Foundry project (az-ai-gateway) as usual.
  2. Copy scripts/agents/_template.json to scripts/agents/<agent-name>.json and
     fill in its 6 fields (see the template for what each one means).
  3. Run:
       AGENT_BASE_URL=https://<this-agent-host>:<port> \
       AGENT_ACCESS_TOKEN=<this Agent's access_token from config.json> \
       python3 scripts/register_agent.py scripts/agents/<agent-name>.json

The script is idempotent: running it again for an already-onboarded agent just
confirms/repairs the wiring instead of duplicating anything.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _call(base_url: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {raw}") from exc


def onboard(base_url: str, token: str, spec: dict) -> None:
    agent_name = spec["agent_name"]
    print(f"== onboarding '{agent_name}' ==")

    print("1/5 مزامنة أصول Foundry (اكتشاف الوكيل من مشروع az-ai-gateway)...")
    _call(base_url, token, "POST", "/ai/api/foundry/sync")

    print("2/5 تسجيله كمشارك في شبكة A2A المحلية...")
    _call(base_url, token, "POST", "/ai/api/a2a/sync")

    print("3/5 تحديث جرد الأدوات المتاحة (production tools)...")
    _call(base_url, token, "POST", "/ai/api/production-tools/discover")
    tools = _call(base_url, token, "GET", "/ai/api/production-tools")
    tools = tools if isinstance(tools, list) else tools.get("tools", [])

    print("4/5 ربط الأدوات المطابقة لفئات هذا الوكيل...")
    categories = spec.get("tool_categories", [])
    explicit_ids = set(spec.get("extra_tool_ids", []))
    bound = 0
    for tool in tools:
        route = str(tool.get("route") or "")
        matches_category = any(f"/{cat}/" in route or route.startswith(f"/{cat}") for cat in categories)
        if matches_category or tool.get("id") in explicit_ids:
            _call(base_url, token, "POST", f"/ai/api/foundry/agents/{agent_name}/tools/{tool['id']}")
            bound += 1
    print(f"    تم ربط {bound} أداة.")

    print("5/5 تجهيز مساحة عمل معزولة لكل تطبيق مسموح به...")
    for app_name in spec.get("bench_apps", []):
        bench_name = spec["bench_name"]
        _call(
            base_url,
            token,
            "POST",
            f"/bench-dev/{bench_name}/{app_name}/agents/{agent_name}/workspace",
        )
        print(f"    مساحة عمل جاهزة: {app_name} (فرع agent/{agent_name.lower()})")

    print(f"\nتم. الدردشة مع '{agent_name}' الآن على: {base_url}/ai/agents/{agent_name}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: register_agent.py scripts/agents/<agent-name>.json", file=sys.stderr)
        return 1
    base_url = os.environ.get("AGENT_BASE_URL")
    token = os.environ.get("AGENT_ACCESS_TOKEN")
    if not base_url or not token:
        print("set AGENT_BASE_URL and AGENT_ACCESS_TOKEN environment variables first", file=sys.stderr)
        return 1
    with open(sys.argv[1], encoding="utf-8") as fh:
        spec = json.load(fh)
    onboard(base_url, token, spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
