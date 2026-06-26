"""FastMCP HTTP server for ``mm serve``."""

from __future__ import annotations

import plistlib
import secrets
import subprocess
import sys
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from fastmcp import FastMCP
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from mcp.server.auth.middleware.bearer_auth import (
    AuthCredentials,
    AuthenticatedUser,
    BearerAuthBackend,
)
from starlette.authentication import AuthenticationBackend
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from mm_cli.applescript import (
    MoneyMoneyLockedError,
    MoneyMoneyNotRunningError,
    create_bank_transfer,
    export_accounts,
    export_categories,
    export_portfolio,
    export_transactions,
    find_category_by_name,
    run_applescript,
    set_transaction_category,
    set_transaction_checkmark,
    set_transaction_comment,
    validate_iban,
)
from mm_cli.config import (
    Config,
    ensure_bearer_token,
    load_config,
    resolve_lan_interface,
    write_config,
)
from mm_cli.models import Account, CategoryType, CategoryUsage, PresenceState

P = ParamSpec("P")
R = TypeVar("R")

LAUNCH_AGENT_LABEL = "de.sussdorff.mm-serve"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _find_console_users(node: object) -> list[Any] | None:
    """Locate the ``IOConsoleUsers`` array within an ioreg plist node.

    ``ioreg -n Root -d1 -a`` may return either a dict (single matched node) or
    a top-level array of matched nodes, and ``IOConsoleUsers`` can be nested one
    level down. Walk the structure defensively so we never call ``.get`` on a
    list (which would raise ``AttributeError``).
    """
    if isinstance(node, dict):
        users = node.get("IOConsoleUsers")
        if users is not None:
            return users if isinstance(users, list) else [users]
        for value in node.values():
            found = _find_console_users(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_console_users(item)
            if found is not None:
                return found
    return None


def is_screen_locked() -> bool:
    """Return whether the console session screen is locked."""
    try:
        result = subprocess.run(
            ["ioreg", "-n", "Root", "-d1", "-a"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        data = plistlib.loads(result.stdout)
        users = _find_console_users(data)
        if not users:
            return False
        first = users[0]
        if not isinstance(first, dict):
            return False
        return bool(first.get("CGSSessionScreenIsLocked"))
    except (plistlib.PListFormatError, OSError, TypeError, IndexError, KeyError):
        return False


def is_moneymoney_running() -> bool:
    """Return whether the MoneyMoney application process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "MoneyMoney"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def activate_moneymoney_and_notify() -> None:
    """Bring MoneyMoney to the foreground and notify the user to unlock."""
    script = """
tell application "MoneyMoney" to activate
display notification "Unlock MoneyMoney to continue" with title "mm serve"
"""
    try:
        run_applescript(script)
    except Exception:
        pass


class PresenceGate:
    """Four-state presence gate before MoneyMoney AppleScript calls."""

    def evaluate(self, *, write: bool = False) -> PresenceState:
        _ = write
        if is_screen_locked():
            return PresenceState.SCREEN_LOCKED
        if not is_moneymoney_running():
            return PresenceState.MM_NOT_RUNNING
        return PresenceState.READY

    def handle_locked_database(self) -> PresenceState:
        activate_moneymoney_and_notify()
        return PresenceState.PENDING_UNLOCK


def presence_error(state: PresenceState) -> dict[str, str]:
    return {"error": state.value, "presence": state.value}


def _account_uuid(account: Account) -> str:
    return account.id


def _serialize_account(account: Account, *, mask_sensitive: bool) -> dict[str, Any]:
    payload = account.to_dict()
    payload["uuid"] = _account_uuid(account)
    if mask_sensitive:
        if payload.get("iban"):
            payload["iban"] = _mask_value(payload["iban"])
        if payload.get("bic"):
            payload["bic"] = _mask_value(payload["bic"])
        if payload.get("account_number"):
            payload["account_number"] = _mask_value(payload["account_number"])
    return payload


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def _resolve_account_by_uuid(account_uuid: str) -> Account | None:
    accounts = export_accounts()
    target = account_uuid.lower()
    for account in accounts:
        if account.id.lower() == target:
            return account
    return None


def _account_identifier(account: Account) -> str:
    return account.iban or account.account_number or account.name


def _compute_category_usage(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 20,
) -> list[CategoryUsage]:
    txs = export_transactions(from_date=from_date, to_date=to_date)
    cats = export_categories()
    cat_types = {cat.id: cat.category_type for cat in cats}
    usage_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total": Decimal("0"), "name": "", "type": CategoryType.EXPENSE}
    )
    for tx in txs:
        if not tx.category_id:
            continue
        key = tx.category_id
        usage_map[key]["count"] += 1
        usage_map[key]["total"] += tx.amount
        usage_map[key]["name"] = tx.category_name or "Unknown"
        usage_map[key]["type"] = cat_types.get(key, CategoryType.EXPENSE)
    usage_list = [
        CategoryUsage(
            category_id=cat_id,
            category_name=data["name"],
            transaction_count=data["count"],
            total_amount=data["total"],
            category_type=data["type"],
        )
        for cat_id, data in usage_map.items()
    ]
    usage_list.sort(key=lambda item: item.transaction_count, reverse=True)
    if limit > 0:
        usage_list = usage_list[:limit]
    return usage_list


class ApiKeyBearerAuthBackend(AuthenticationBackend):
    """Accept bearer tokens from Authorization or X-Api-Key headers."""

    def __init__(self, token_verifier: DebugTokenVerifier) -> None:
        self._backend = BearerAuthBackend(token_verifier)

    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, AuthenticatedUser] | None:
        auth_header = next(
            (conn.headers.get(key) for key in conn.headers if key.lower() == "authorization"),
            None,
        )
        api_key = next(
            (conn.headers.get(key) for key in conn.headers if key.lower() == "x-api-key"),
            None,
        )
        if (not auth_header or not auth_header.lower().startswith("bearer ")) and api_key:
            scope = dict(conn.scope)
            headers = list(scope.get("headers", []))
            headers.append((b"authorization", b"Bearer " + api_key.encode("utf-8")))
            scope["headers"] = headers
            conn = HTTPConnection(scope)
        return await self._backend.authenticate(conn)


class ApiKeyBearerMiddleware:
    """ASGI shim retained for tests that wrap apps manually."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = list(scope.get("headers", []))
            auth_present = any(name.lower() == b"authorization" for name, _value in headers)
            if not auth_present:
                api_key = next(
                    (value for name, value in headers if name.lower() == b"x-api-key"),
                    None,
                )
                if api_key:
                    headers.append((b"authorization", b"Bearer " + api_key))
                    scope = dict(scope)
                    scope["headers"] = headers
        await self.app(scope, receive, send)


def _make_token_verifier(expected_token: str) -> DebugTokenVerifier:
    def _validate(token: str) -> bool:
        return secrets.compare_digest(token, expected_token)

    return DebugTokenVerifier(validate=_validate)


def _presence_guard(
    gate: PresenceGate,
    *,
    write: bool,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | dict[str, str]]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | dict[str, str]]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, str]:
            state = gate.evaluate(write=write)
            if state is not PresenceState.READY:
                return presence_error(state)
            try:
                return await func(*args, **kwargs)
            except MoneyMoneyLockedError:
                return presence_error(gate.handle_locked_database())
            except MoneyMoneyNotRunningError:
                return presence_error(PresenceState.MM_NOT_RUNNING)

        return wrapper

    return decorator


def create_mcp_server(
    *,
    config_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    mask_sensitive: bool | None = None,
) -> FastMCP:
    """Create a configured FastMCP server instance."""
    config = load_config(config_path)
    if mask_sensitive is not None:
        config = Config(
            transfer_category=config.transfer_category,
            excluded_groups=list(config.excluded_groups),
            bearer_token=config.bearer_token,
            lan_interface=config.lan_interface,
            serve_port=config.serve_port,
            mask_sensitive=mask_sensitive,
        )
    if not config.bearer_token:
        raise ValueError("bearer_token is required for mm serve")

    gate = PresenceGate()
    auth = _make_token_verifier(config.bearer_token)
    mcp = FastMCP("mm-serve", auth=auth)
    bind_host = host or resolve_lan_interface(config)
    bind_port = port if port is not None else config.serve_port
    mcp._mm_bind_host = bind_host  # type: ignore[attr-defined]
    mcp._mm_bind_port = bind_port  # type: ignore[attr-defined]

    @mcp.tool(name="list_accounts")
    @_presence_guard(gate, write=False)
    async def list_accounts() -> Any:
        return [_serialize_account(acc, mask_sensitive=config.mask_sensitive) for acc in export_accounts()]

    @mcp.tool(name="list_categories")
    @_presence_guard(gate, write=False)
    async def list_categories() -> Any:
        return [cat.to_dict() for cat in export_categories()]

    @mcp.tool(name="list_transactions")
    @_presence_guard(gate, write=False)
    async def list_transactions(
        account_uuid: str | None = None,
        days: int = 14,
    ) -> Any:
        end = date.today()
        start = end - timedelta(days=days)
        txs = export_transactions(account_id=account_uuid, from_date=start, to_date=end)
        return [tx.to_dict() for tx in txs]

    @mcp.tool(name="list_portfolio")
    @_presence_guard(gate, write=False)
    async def list_portfolio() -> Any:
        return [portfolio.to_dict() for portfolio in export_portfolio()]

    @mcp.tool(name="category_usage")
    @_presence_guard(gate, write=False)
    async def category_usage(days: int = 30, limit: int = 20) -> Any:
        end = date.today()
        start = end - timedelta(days=days)
        usage = _compute_category_usage(from_date=start, to_date=end, limit=limit)
        return [item.to_dict() for item in usage]

    @mcp.tool(name="set_category")
    @_presence_guard(gate, write=True)
    async def set_category(transaction_id: str, category: str) -> dict[str, Any]:
        if len(category) < 32 or "-" not in category:
            cat = find_category_by_name(category)
            if not cat:
                return {"error": f"category_not_found: {category}"}
            category_id = cat.id
        else:
            category_id = category
        set_transaction_category(transaction_id, category_id)
        return {"ok": True, "transaction_id": transaction_id, "category_id": category_id}

    @mcp.tool(name="set_checkmark")
    @_presence_guard(gate, write=True)
    async def set_checkmark(transaction_id: str, state: str) -> dict[str, Any]:
        if state not in ("on", "off"):
            return {"error": "invalid_state"}
        set_transaction_checkmark(transaction_id, checked=state == "on")
        return {"ok": True, "transaction_id": transaction_id, "checkmark": state}

    @mcp.tool(name="set_comment")
    @_presence_guard(gate, write=True)
    async def set_comment(transaction_id: str, comment: str) -> dict[str, Any]:
        set_transaction_comment(transaction_id, comment)
        return {"ok": True, "transaction_id": transaction_id}

    @mcp.tool(name="transfer")
    @_presence_guard(gate, write=True)
    async def transfer(
        source_account_uuid: str,
        recipient: str,
        iban: str,
        amount: float,
        purpose: str,
    ) -> dict[str, Any]:
        if amount <= 0:
            return {"error": "amount_must_be_positive"}
        try:
            normalized_iban = validate_iban(iban)
        except ValueError as exc:
            return {"error": str(exc)}
        account = _resolve_account_by_uuid(source_account_uuid)
        if account is None:
            return {"error": f"account_not_found: {source_account_uuid}"}
        create_bank_transfer(
            account_number=_account_identifier(account),
            recipient=recipient,
            iban=normalized_iban,
            amount=amount,
            purpose=purpose,
            outbox=True,
        )
        return {
            "ok": True,
            "outbox": True,
            "source_account_uuid": source_account_uuid,
            "recipient": recipient,
            "iban": normalized_iban,
            "amount": amount,
        }

    original_http_app = mcp.http_app

    def http_app_with_api_key(*args: Any, **kwargs: Any) -> Any:
        app = original_http_app(*args, **kwargs)
        return ApiKeyBearerMiddleware(app)

    mcp.http_app = http_app_with_api_key  # type: ignore[method-assign]
    mcp._mm_api_key_backend = ApiKeyBearerAuthBackend(auth)  # type: ignore[attr-defined]
    return mcp


def run_server(
    *,
    config_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    transport: str = "streamable-http",
    mask_sensitive: bool | None = None,
) -> None:
    """Run the MCP HTTP server."""
    config = load_config(config_path)
    config, _generated = ensure_bearer_token(config, path=config_path)
    if mask_sensitive is not None:
        config = Config(
            transfer_category=config.transfer_category,
            excluded_groups=list(config.excluded_groups),
            bearer_token=config.bearer_token,
            lan_interface=config.lan_interface,
            serve_port=config.serve_port,
            mask_sensitive=mask_sensitive,
        )
    bind_host = host or resolve_lan_interface(config)
    if bind_host in ("0.0.0.0", "::", "[::]"):
        raise ValueError("mm serve must bind to a specific LAN interface, not a wildcard address")
    bind_port = port if port is not None else config.serve_port
    mcp = create_mcp_server(
        config_path=config_path,
        host=bind_host,
        port=bind_port,
        mask_sensitive=config.mask_sensitive,
    )
    mcp.run(transport=transport, host=bind_host, port=bind_port)


def install_launch_agent(*, config_path: Path | None = None) -> Path:
    """Install LaunchAgent plist for GUI-session auto-start."""
    config = load_config(config_path)
    config, _generated = ensure_bearer_token(config, path=config_path)
    if not config.lan_interface:
        config = Config(
            transfer_category=config.transfer_category,
            excluded_groups=list(config.excluded_groups),
            bearer_token=config.bearer_token,
            lan_interface=resolve_lan_interface(config),
            serve_port=config.serve_port,
            mask_sensitive=config.mask_sensitive,
        )
        write_config(config, path=config_path)

    python_path = sys.executable
    args = ["serve"]
    if config_path is not None:
        args.extend(["--config", str(config_path)])

    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [python_path, "-m", "mm_cli.cli", *args],
        "RunAtLoad": True,
        "KeepAlive": True,
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "mm-serve.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "mm-serve.err.log"),
    }
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LAUNCH_AGENT_PATH.open("wb") as handle:
        plistlib.dump(plist, handle)

    uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(LAUNCH_AGENT_PATH)], check=False)
    subprocess.run(["launchctl", "bootstrap", domain, str(LAUNCH_AGENT_PATH)], check=True)
    subprocess.run(["launchctl", "enable", f"{domain}/{LAUNCH_AGENT_LABEL}"], check=False)
    return LAUNCH_AGENT_PATH


def uninstall_launch_agent() -> None:
    """Unload and remove the LaunchAgent plist."""
    if LAUNCH_AGENT_PATH.exists():
        uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
        domain = f"gui/{uid}"
        subprocess.run(["launchctl", "bootout", domain, str(LAUNCH_AGENT_PATH)], check=False)
        LAUNCH_AGENT_PATH.unlink(missing_ok=True)
