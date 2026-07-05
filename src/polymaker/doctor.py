"""Preflight checks for `polymaker doctor`.

Verifies the environment is ready to trade WITHOUT posting any order:
config + secrets, CLOB/Gamma reachable, wallet auth (L1->L2 creds), collateral
balance + positions ON THE FUNDER (deposit/developer wallet, where funds live),
a live market-WS book frame, and an authenticated user-WS connection. This is
the gate before the live $5 round-trip (the README).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import websockets
from rich.console import Console

from polymaker.config import Config

MARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
USER_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/user"


async def run_doctor(cfg: Config, console: Console) -> bool:
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "[green]✓[/green]" if passed else "[red]✗[/red]"
        console.print(f"  {mark} {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))
        ok = ok and passed

    console.print("[bold]polymaker doctor[/bold]")

    # ── config + secrets ────────────────────────────────────────────────
    check("config loads", True, f"{len(cfg.profiles)} profiles, {len(cfg.markets)} markets")
    check("PK + BROWSER_ADDRESS set", cfg.secrets.has_wallet,
          "put them in .env" if not cfg.secrets.has_wallet
          else f"funder {cfg.secrets.browser_address[:10]}…, sig_type {cfg.wallet.signature_type}")

    # ── REST reachability ───────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(f"{cfg.wallet.clob_host}/ok")
            check("CLOB reachable", r.status_code == 200, cfg.wallet.clob_host)
        except httpx.HTTPError as e:
            check("CLOB reachable", False, str(e))
        try:
            r = await c.get(f"{cfg.wallet.gamma_host}/markets", params={"limit": 1})
            check("Gamma reachable", r.status_code == 200, cfg.wallet.gamma_host)
        except httpx.HTTPError as e:
            check("Gamma reachable", False, str(e))

    # ── wallet auth + balance + positions (on the FUNDER) ───────────────
    creds: Any = None
    funder = ""
    held_tokens: list[str] = []
    if cfg.secrets.has_wallet:
        try:
            from polymaker.execution.gateway import ExecutionGateway

            gw = ExecutionGateway(cfg)
            await gw.connect()
            creds = gw.creds
            funder = gw.funder
            check("wallet auth (L2 creds derived)", bool(gw.creds),
                  f"signer {gw.address[:10]}… signs for funder {funder[:10]}…")

            ba = await gw.balance_allowance()
            bal = _extract_balance(ba)
            check("collateral (pUSD) balance readable", bal is not None,
                  f"≈{bal:.2f} pUSD on funder {funder[:10]}…" if bal is not None else "check allowances")
            if bal is not None and bal <= 0:
                console.print("  [yellow]! balance is 0 — deposit USDC (mints pUSD) and set "
                              "allowances from the deposit wallet (trade once in the UI)[/yellow]")

            positions = await gw.positions()
            held_tokens = list(positions)
            total_shares = sum(sz for sz, _ in positions.values())
            check("positions readable (on funder)", True,
                  f"{len(positions)} positions, {total_shares:.0f} shares total")
        except Exception as e:  # noqa: BLE001
            check("wallet auth (L2 creds derived)", False, str(e))
            console.print("  [yellow]! signature-type mismatch? deposit wallets use sig_type=3 "
                          "(config.toml). See the README.[/yellow]")
    else:
        console.print("  [yellow]! skipping wallet checks (no secrets)[/yellow]")

    if cfg.proxy:
        console.print(f"  [dim]· routing via proxy {cfg.proxy.split('@')[-1]}[/dim]")

    # ── live market WS: receive an actual book frame ────────────────────
    token = held_tokens[0] if held_tokens else await _top_political_token(cfg)
    if token:
        passed, detail = await _market_ws_book(token, cfg.proxy)
        check("market WS live book frame", passed, detail)
    else:
        check("market WS live book frame", False, "no token to subscribe to")

    # ── live user WS: authenticate ──────────────────────────────────────
    if creds is not None:
        markets = [cfg.markets[0].condition_id] if cfg.markets and cfg.markets[0].condition_id else []
        passed, detail = await _user_ws_auth(creds, markets, cfg.proxy)
        check("user WS authenticated", passed, detail)
    else:
        console.print("  [dim]· skipping user WS (needs wallet creds)[/dim]")

    console.print(f"\n[bold]{'READY' if ok else 'NOT READY'}[/bold]")
    return ok


async def _market_ws_book(token: str, proxy: str | None = None) -> tuple[bool, str]:
    """Subscribe to a token and confirm a real `book` frame arrives."""
    kw: dict[str, Any] = {"ping_interval": 5, "ping_timeout": None, "open_timeout": 10}
    if proxy:
        kw["proxy"] = proxy
    try:
        async with websockets.connect(MARKET_WS, **kw) as ws:
            await ws.send(json.dumps({"assets_ids": [token], "type": "market"}))
            for _ in range(12):
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                data = json.loads(raw)
                for m in data if isinstance(data, list) else [data]:
                    if isinstance(m, dict) and m.get("event_type") == "book":
                        nb, na = len(m.get("bids", [])), len(m.get("asks", []))
                        return True, f"book received: {nb} bids / {na} asks"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]
    return False, "no book frame within timeout"


async def _user_ws_auth(creds: Any, markets: list[str], proxy: str | None = None) -> tuple[bool, str]:
    """Authenticate on the user channel and confirm the server accepts it."""
    kw: dict[str, Any] = {"ping_interval": 5, "ping_timeout": None, "open_timeout": 10}
    if proxy:
        kw["proxy"] = proxy
    try:
        async with websockets.connect(USER_WS, **kw) as ws:
            await ws.send(json.dumps({
                "type": "user",
                "auth": {"apiKey": creds.api_key, "secret": creds.api_secret,
                         "passphrase": creds.api_passphrase},
                "markets": markets,
            }))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=4)
                low = raw.lower() if isinstance(raw, str) else ""
                if "auth" in low and any(w in low for w in ("fail", "error", "invalid", "unauthor")):
                    return False, "auth rejected by server"
                return True, "connected, receiving events"
            except TimeoutError:
                # no message but the socket stayed open => auth accepted, just idle
                return True, "connected (idle — no events yet)"
    except websockets.ConnectionClosed:
        return False, "connection closed (auth likely rejected)"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]


async def _top_political_token(cfg: Config) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{cfg.wallet.gamma_host}/markets",
                            params={"limit": 1, "closed": "false", "tag_id": 2,
                                    "order": "volume24hr", "ascending": "false"})
            toks = json.loads(r.json()[0]["clobTokenIds"])
            return str(toks[0])
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None


def _extract_balance(ba: dict[str, Any]) -> float | None:
    if not isinstance(ba, dict):
        return None
    for k in ("balance", "collateral", "amount"):
        if k in ba:
            try:
                v = float(ba[k])
                return v / 1e6 if v > 1e6 else v
            except (ValueError, TypeError):
                return None
    return None
