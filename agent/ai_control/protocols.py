from __future__ import annotations

import json
import time
from typing import Any

import requests

from agent.ai_control.models import AIIntegrationModel


class ProtocolTestError(RuntimeError):
    pass


def _headers(integration: AIIntegrationModel) -> dict[str, str]:
    # Secret values are deliberately not stored on the integration record.
    # The configured secret_ref will be resolved by a credential provider in a later patch.
    return {"Accept": "application/json"}


def test_api(integration: AIIntegrationModel) -> dict[str, Any]:
    if not integration.endpoint:
        raise ProtocolTestError("API endpoint is required")
    started = time.monotonic()
    response = requests.get(integration.endpoint, headers=_headers(integration), timeout=20)
    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "preview": response.text[:5000],
    }


def test_webhook(integration: AIIntegrationModel) -> dict[str, Any]:
    if not integration.endpoint:
        raise ProtocolTestError("Webhook target endpoint is required")
    config = json.loads(integration.config or "{}")
    payload = config.get("test_payload") or {"source": "agent-ai-control", "event": "test"}
    started = time.monotonic()
    response = requests.post(
        integration.endpoint,
        json=payload,
        headers={**_headers(integration), "Content-Type": "application/json"},
        timeout=20,
    )
    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "preview": response.text[:5000],
    }


def test_mcp(integration: AIIntegrationModel) -> dict[str, Any]:
    """MCP is intentionally delegated to the official SDK in the next protocol patch.

    We do not hand-roll the MCP wire protocol here because protocol versions and
    transports evolve. The UI and persisted contract are ready; runtime enablement
    will use the official MCP client implementation.
    """
    raise ProtocolTestError("MCP runtime client is not enabled in this patch")


def test_a2a(integration: AIIntegrationModel) -> dict[str, Any]:
    """Validate standard A2A Agent Card discovery without auto-trusting the peer.

    This is a discovery/compatibility check only. Routing an external A2A peer still
    requires explicit participant registration and trust in the A2A control plane.
    """
    if not integration.endpoint:
        raise ProtocolTestError("A2A endpoint is required")
    base = integration.endpoint.strip().rstrip("/")
    if base.endswith("/.well-known/agent-card.json"):
        card_url = base
    else:
        card_url = f"{base}/.well-known/agent-card.json"
    started = time.monotonic()
    response = requests.get(card_url, headers=_headers(integration), timeout=20)
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if not response.ok:
        return {
            "ok": False,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "agent_card_url": card_url,
            "preview": response.text[:5000],
        }
    try:
        card = response.json()
    except ValueError as exc:
        raise ProtocolTestError(f"A2A Agent Card is not valid JSON: {exc}") from exc
    name = card.get("name") if isinstance(card, dict) else None
    interfaces = []
    if isinstance(card, dict):
        interfaces = card.get("supportedInterfaces") or card.get("supported_interfaces") or []
    if not name or not isinstance(interfaces, list) or not interfaces:
        raise ProtocolTestError("A2A Agent Card is missing name or supported interfaces")
    return {
        "ok": True,
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "agent_card_url": card_url,
        "agent": name,
        "supported_interfaces": interfaces,
        "discovery_only": True,
    }


def test_ai_tool(integration: AIIntegrationModel) -> dict[str, Any]:
    raise ProtocolTestError("AI Tool execution requires a linked Foundry tool/toolbox")


def test_integration(integration: AIIntegrationModel) -> dict[str, Any]:
    handlers = {
        "api": test_api,
        "webhook": test_webhook,
        "mcp": test_mcp,
        "a2a": test_a2a,
        "ai_tool": test_ai_tool,
    }
    handler = handlers.get(integration.integration_type)
    if not handler:
        raise ProtocolTestError(f"No tester for {integration.integration_type}")
    return handler(integration)
