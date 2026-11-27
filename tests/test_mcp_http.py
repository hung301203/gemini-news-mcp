"""End-to-end tests for Stateless Streamable HTTP MCP protocol & Render health route."""

import json

import httpx
from starlette.testclient import TestClient

from gemini_news_mcp.config import Settings
from gemini_news_mcp.server import create_server


def _mcp_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def test_health_and_streamable_http_initialize_and_list_tools() -> None:
    _, app, _ = create_server(Settings(mcp_path_secret="", rate_limit_rpm=100))

    with TestClient(app) as client:
        # 1. Health check endpoint for Render
        h = client.get("/health")
        assert h.status_code == 200
        body = h.json()
        assert body["status"] == "ok"
        assert body["transport"] == "streamable-http-stateless"

        # 2. MCP initialize over Streamable HTTP
        init_resp = client.post(
            "/mcp",
            headers=_mcp_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "gemini-web-test", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        init_json = init_resp.json()
        assert init_json["result"]["serverInfo"]["name"] == "gemini-news-mcp"

        # 3. Stateless tools/list call (no session header needed!)
        tools_resp = client.post(
            "/mcp",
            headers=_mcp_headers(),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert tools_resp.status_code == 200
        tools = tools_resp.json()["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {
            "get_daily_briefing",
            "get_automation_news",
            "get_market_movers_and_drivers",
            "get_wellness_updates",
            "search_current_affairs",
            "read_article",
        }


def test_secret_path_protects_mcp_endpoint() -> None:
    _, app, _ = create_server(Settings(mcp_path_secret="super-secret-token-123", rate_limit_rpm=100))

    with TestClient(app) as client:
        # Default /mcp should not be exposed when secret is set
        blocked = client.post(
            "/mcp",
            headers=_mcp_headers(),
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert blocked.status_code == 404

        # Secret path works
        ok = client.post(
            "/mcp/super-secret-token-123",
            headers=_mcp_headers(),
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert ok.status_code == 200
        assert len(ok.json()["result"]["tools"]) == 6


def test_read_article_tool_rejects_ssrf_via_mcp_call() -> None:
    _, app, _ = create_server(Settings(mcp_path_secret="", rate_limit_rpm=100))

    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers=_mcp_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "read_article",
                    "arguments": {"url": "http://127.0.0.1:8000/health"},
                },
            },
        )
        assert resp.status_code == 200
        content_text = resp.json()["result"]["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["ok"] is False
        assert "Blocked by security policy" in parsed["error"]
