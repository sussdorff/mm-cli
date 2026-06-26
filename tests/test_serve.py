"""Tests for mm serve MCP server."""

from __future__ import annotations

import asyncio
import plistlib
import socket
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    Portfolio,
    Security,
    Transaction,
)


@pytest.fixture
def serve_token() -> str:
    return "test-bearer-token-hex-64-chars-long-enough-for-auth-check-1234567890ab"


@pytest.fixture
def serve_config(tmp_path: Path, serve_token: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'bearer_token = "' + serve_token + '"',
                'lan_interface = "127.0.0.1"',
                "serve_port = 0",
                "mask_sensitive = false",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def running_server(serve_config: Path, serve_token: str):
    """Start MCP server on ephemeral port for integration tests."""
    from mm_cli.serve import create_mcp_server

    port = _free_port()
    mcp = create_mcp_server(config_path=serve_config, host="127.0.0.1", port=port)
    app = mcp.http_app(transport="streamable-http")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}/mcp", serve_token, server
    server.should_exit = True
    thread.join(timeout=2)


class TestAC1ServerEndpoint:
    """AC1: reachable Streamable-HTTP MCP endpoint lists tools."""

    def test_server_lists_tools_with_valid_token(self, running_server) -> None:
        url, token, _server = running_server

        async def _list_tools() -> list[str]:
            transport = StreamableHttpTransport(url, auth=token)
            async with Client(transport) as client:
                tools = await client.list_tools()
                return [tool.name for tool in tools]

        tool_names = asyncio.run(_list_tools())
        assert "list_accounts" in tool_names
        assert "list_transactions" in tool_names
        assert "transfer" in tool_names

    def test_server_rejects_missing_token(self, running_server) -> None:
        url, _token, _server = running_server

        async def _post_without_auth() -> int:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "id": 1,
                        "params": {},
                    },
                )
                return response.status_code

        assert asyncio.run(_post_without_auth()) == 401
