"""Tests for mm serve MCP server."""

from __future__ import annotations

import asyncio
import json
import plistlib
import socket
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from mm_cli.applescript import MoneyMoneyLockedError


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


def _tool_result_data(result: Any) -> Any:
    """Extract structured tool output (FastMCP sets .data for dicts, JSON text for lists)."""
    if result.data is not None:
        return result.data
    if result.content:
        text = getattr(result.content[0], "text", None)
        if text:
            return json.loads(text)
    if result.is_error:
        raise AssertionError(f"Tool error: {result.content}")
    return None


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


class TestAC2ReadToolsUuid:
    """AC2: read tools return structured data with account UUID handle."""

    @patch("mm_cli.serve.is_screen_locked", return_value=False)
    @patch("mm_cli.serve.is_moneymoney_running", return_value=True)
    @patch("mm_cli.serve.export_accounts")
    @patch("mm_cli.serve.export_transactions")
    @patch("mm_cli.serve.export_portfolio")
    @patch("mm_cli.serve.export_categories")
    def test_read_tools_return_uuid(
        self,
        mock_categories: MagicMock,
        mock_portfolio: MagicMock,
        mock_transactions: MagicMock,
        mock_accounts: MagicMock,
        _mock_mm: MagicMock,
        _mock_screen: MagicMock,
        running_server,
        sample_accounts,
        sample_transactions,
        sample_portfolios,
        sample_categories,
    ) -> None:
        url, token, _server = running_server
        mock_accounts.return_value = sample_accounts
        mock_transactions.return_value = sample_transactions
        mock_portfolio.return_value = sample_portfolios
        mock_categories.return_value = sample_categories

        async def _call_tools() -> dict[str, object]:
            transport = StreamableHttpTransport(url, auth=token)
            async with Client(transport) as client:
                accounts = await client.call_tool("list_accounts", {})
                transactions = await client.call_tool("list_transactions", {})
                portfolio = await client.call_tool("list_portfolio", {})
                categories = await client.call_tool("list_categories", {})
                usage = await client.call_tool("category_usage", {})
                return {
                    "accounts": _tool_result_data(accounts),
                    "transactions": _tool_result_data(transactions),
                    "portfolio": _tool_result_data(portfolio),
                    "categories": _tool_result_data(categories),
                    "usage": _tool_result_data(usage),
                }

        results = asyncio.run(_call_tools())
        for account in results["accounts"]:  # type: ignore[index]
            assert "uuid" in account
            assert account["uuid"] == account["id"]
        for item in results["portfolio"]:  # type: ignore[index]
            assert "account_id" in item


class TestAC3PresenceGate:
    """AC3: presence gating for screen lock, MM state, and unlock flow."""

    def test_screen_locked_blocks_applescript(self) -> None:
        from mm_cli.models import PresenceState
        from mm_cli.serve import PresenceGate, presence_error

        gate = PresenceGate()
        with (
            patch("mm_cli.serve.is_screen_locked", return_value=True),
            patch("mm_cli.serve.is_moneymoney_running", return_value=True),
            patch("mm_cli.serve.export_accounts") as mock_export,
        ):
            state = gate.evaluate()
            assert state == PresenceState.SCREEN_LOCKED
            assert presence_error(state)["presence"] == "screen_locked"
            mock_export.assert_not_called()

    def test_mm_not_running(self) -> None:
        from mm_cli.models import PresenceState
        from mm_cli.serve import PresenceGate

        gate = PresenceGate()
        with (
            patch("mm_cli.serve.is_screen_locked", return_value=False),
            patch("mm_cli.serve.is_moneymoney_running", return_value=False),
        ):
            assert gate.evaluate() == PresenceState.MM_NOT_RUNNING

    @patch("mm_cli.serve.activate_moneymoney_and_notify")
    def test_pending_unlock_on_locked_database(self, mock_notify: MagicMock) -> None:
        from mm_cli.models import PresenceState
        from mm_cli.serve import PresenceGate

        gate = PresenceGate()
        assert gate.handle_locked_database() == PresenceState.PENDING_UNLOCK
        mock_notify.assert_called_once()

    @patch("mm_cli.serve.is_screen_locked", return_value=False)
    @patch("mm_cli.serve.is_moneymoney_running", return_value=True)
    @patch("mm_cli.serve.export_accounts", side_effect=MoneyMoneyLockedError("locked"))
    @patch("mm_cli.serve.activate_moneymoney_and_notify")
    def test_tool_returns_pending_unlock(
        self,
        mock_notify: MagicMock,
        _mock_export: MagicMock,
        _mock_mm: MagicMock,
        _mock_screen: MagicMock,
        running_server,
    ) -> None:
        url, token, _server = running_server

        async def _call() -> dict[str, str]:
            transport = StreamableHttpTransport(url, auth=token)
            async with Client(transport) as client:
                result = await client.call_tool("list_accounts", {})
                return _tool_result_data(result)

        data = asyncio.run(_call())
        assert data["presence"] == "pending_unlock"
        mock_notify.assert_called_once()


class TestAC4WriteSafety:
    """AC4: transfer outbox-only; metadata writes; UUID-addressed transfer."""

    @patch("mm_cli.serve.is_screen_locked", return_value=False)
    @patch("mm_cli.serve.is_moneymoney_running", return_value=True)
    @patch("mm_cli.serve.create_bank_transfer")
    @patch("mm_cli.serve.export_accounts")
    def test_transfer_outbox_only(
        self,
        mock_accounts: MagicMock,
        mock_transfer: MagicMock,
        _mock_mm: MagicMock,
        _mock_screen: MagicMock,
        running_server,
        sample_accounts,
    ) -> None:
        url, token, _server = running_server
        mock_accounts.return_value = sample_accounts

        async def _call() -> dict[str, object]:
            transport = StreamableHttpTransport(url, auth=token)
            async with Client(transport) as client:
                result = await client.call_tool(
                    "transfer",
                    {
                        "source_account_uuid": sample_accounts[0].id,
                        "recipient": "Max",
                        "iban": "DE89370400440532013000",
                        "amount": 10.0,
                        "purpose": "test",
                    },
                )
                return result.data  # type: ignore[return-value]

        data = asyncio.run(_call())
        assert data["ok"] is True
        assert data["outbox"] is True
        mock_transfer.assert_called_once()
        assert mock_transfer.call_args.kwargs["outbox"] is True

    @patch("mm_cli.serve.is_screen_locked", return_value=False)
    @patch("mm_cli.serve.is_moneymoney_running", return_value=True)
    @patch("mm_cli.serve.set_transaction_comment")
    def test_metadata_write_direct(
        self,
        mock_comment: MagicMock,
        _mock_mm: MagicMock,
        _mock_screen: MagicMock,
        running_server,
    ) -> None:
        url, token, _server = running_server

        async def _call() -> dict[str, object]:
            transport = StreamableHttpTransport(url, auth=token)
            async with Client(transport) as client:
                result = await client.call_tool(
                    "set_comment",
                    {"transaction_id": "12345", "comment": "reviewed"},
                )
                return result.data  # type: ignore[return-value]

        data = asyncio.run(_call())
        assert data["ok"] is True
        mock_comment.assert_called_once_with("12345", "reviewed")


class TestAC5AuthAndBind:
    """AC5: reject missing token; bind to specific LAN interface."""

    def test_auth_required_via_api_key_header(self, running_server) -> None:
        url, token, _server = running_server

        async def _call_with_api_key() -> int:
            transport = StreamableHttpTransport(url, headers={"X-Api-Key": token})
            async with Client(transport) as client:
                tools = await client.list_tools()
                return len(tools)

        assert asyncio.run(_call_with_api_key()) >= 1

    def test_server_rejects_invalid_token(self, running_server) -> None:
        url, _token, _server = running_server

        async def _post_with_wrong_token() -> int:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": "Bearer "
                        + "wrong-token-0000000000000000000000000000000000000000000000000000"
                    },
                    json={
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "id": 1,
                        "params": {},
                    },
                )
                return response.status_code

        assert asyncio.run(_post_with_wrong_token()) == 401

    def test_lan_bind_not_wildcard(self, serve_config: Path) -> None:
        from mm_cli.serve import create_mcp_server

        mcp = create_mcp_server(config_path=serve_config, host="127.0.0.1", port=0)
        assert mcp._mm_bind_host == "127.0.0.1"  # type: ignore[attr-defined]
        assert mcp._mm_bind_host not in ("0.0.0.0", "::")  # type: ignore[attr-defined]

    def test_run_server_rejects_wildcard_bind(self, serve_config: Path) -> None:
        from mm_cli.serve import run_server

        with pytest.raises(ValueError, match="wildcard"):
            run_server(config_path=serve_config, host="0.0.0.0", port=8765)


class TestAC6Deploy:
    """AC6: LaunchAgent install/uninstall."""

    def test_install_writes_launch_agent_plist(self, tmp_path: Path, serve_token: str) -> None:
        from mm_cli.serve import install_launch_agent

        config_path = tmp_path / "config.toml"
        config_path.write_text(
            f'bearer_token = "{serve_token}"\nlan_interface = "127.0.0.1"\n',
            encoding="utf-8",
        )
        fake_plist = tmp_path / "agent.plist"

        with (
            patch("mm_cli.serve.LAUNCH_AGENT_PATH", fake_plist),
            patch("mm_cli.serve.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout="501", returncode=0)
            path = install_launch_agent(config_path=config_path)

        assert path == fake_plist
        assert fake_plist.exists()
        payload = plistlib.loads(fake_plist.read_bytes())
        assert payload["Label"] == "de.sussdorff.mm-serve"
        assert payload["LimitLoadToSessionType"] == "Aqua"
        assert "serve" in payload["ProgramArguments"]

    def test_uninstall_removes_plist(self, tmp_path: Path) -> None:
        from mm_cli.serve import uninstall_launch_agent

        fake_plist = tmp_path / "agent.plist"
        fake_plist.write_bytes(plistlib.dumps({"Label": "de.sussdorff.mm-serve"}))

        with (
            patch("mm_cli.serve.LAUNCH_AGENT_PATH", fake_plist),
            patch("mm_cli.serve.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout="501", returncode=0)
            uninstall_launch_agent()

        assert not fake_plist.exists()


class TestAC7Masking:
    """AC7 (optional): mask IBAN while preserving UUID."""

    @patch("mm_cli.serve.is_screen_locked", return_value=False)
    @patch("mm_cli.serve.is_moneymoney_running", return_value=True)
    @patch("mm_cli.serve.export_accounts")
    def test_masking_redacts_iban_keeps_uuid(
        self,
        mock_accounts: MagicMock,
        _mock_mm: MagicMock,
        _mock_screen: MagicMock,
        serve_config: Path,
        serve_token: str,
        sample_accounts,
    ) -> None:
        from mm_cli.serve import create_mcp_server

        mock_accounts.return_value = sample_accounts
        port = _free_port()
        mcp = create_mcp_server(
            config_path=serve_config,
            host="127.0.0.1",
            port=port,
            mask_sensitive=True,
        )
        app = mcp.http_app(transport="streamable-http")
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        time.sleep(0.5)

        async def _call() -> Any:
            url = f"http://127.0.0.1:{port}/mcp"
            transport = StreamableHttpTransport(url, auth=serve_token)
            async with Client(transport) as client:
                return await client.call_tool("list_accounts", {})

        try:
            accounts = _tool_result_data(asyncio.run(_call()))
            assert accounts[0]["uuid"] == sample_accounts[0].id
            assert "DE89" not in accounts[0]["iban"]
            assert accounts[0]["iban"].endswith("3000")
        finally:
            server.should_exit = True
            thread.join(timeout=2)
