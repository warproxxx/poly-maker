"""Live wallet round-trip test — the Phase-2 wallet spike (see the README).

Proves the full V2 order path against the real exchange with minimal risk:
places ONE post-only BUY well below the touch (so it rests and cannot fill),
confirms it appears in open orders, then cancels it. Post-only guarantees it
never takes; the deep price + immediate cancel means ~zero economic risk.

This is where the known py-clob-client-v2 signature-type-2 (Safe/proxy) issues
would surface — the command reports each step so failures are diagnosable.
"""

from __future__ import annotations

import asyncio

from rich.console import Console

from polymaker.config import Config
from polymaker.domain import Quote, Side
from polymaker.execution.gateway import ExecutionGateway


async def run_livetest(cfg: Config, console: Console, notional_usdc: float = 5.0) -> bool:
    from polymaker.catalog.store import CatalogStore

    if not cfg.secrets.has_wallet:
        console.print("[red]No wallet in .env. Set PK and BROWSER_ADDRESS first.[/red]")
        return False

    # pick a liquid market from the catalog (or fall back to a live scan)
    store = CatalogStore(cfg.paths.db)
    rows = store.top(20)
    store.close()
    if not rows:
        console.print("[yellow]Catalog empty — run `polymaker scan` first.[/yellow]")
        return False
    # choose a market with a mid comfortably in (0.15, 0.85) so a deep bid is valid
    meta = None
    for m, _sc in rows:
        mid = (m.best_bid + m.best_ask) / 2 if (m.best_bid and m.best_ask) else 0.0
        if 0.15 < mid < 0.85:
            meta = m
            break
    meta = meta or rows[0][0]

    console.print(f"[bold]Live round-trip test[/bold] on: {meta.question[:60]}")
    gw = ExecutionGateway(cfg)
    try:
        await gw.connect()
        console.print(f"  [green]✓[/green] wallet auth — address {gw.address[:12]}…")
    except Exception as e:  # noqa: BLE001
        console.print(f"  [red]✗ wallet auth failed:[/red] {e}")
        console.print("  [yellow]Auth/signature-type mismatch (see the README). If your account has a "
                      "'deposit address', set signature_type=3 (POLY_1271) in config.toml and use the "
                      "deposit address as BROWSER_ADDRESS. Errors like 'maker address not allowed, use "
                      "the deposit wallet flow' or 'signer must be the API key address' mean the type is "
                      "wrong for this wallet.[/yellow]")
        return False

    ba = await gw.balance_allowance()
    console.print(f"  balance/allowance: {ba}")

    # a deep resting price: well below best bid, snapped to tick, floored at 2 ticks
    tick = meta.tick_size
    best_bid = meta.best_bid or 0.30
    price = max(2 * tick, round((best_bid - 0.10) / tick) * tick)
    size = round(max(meta.min_order_size, notional_usdc / price), 2)
    console.print(f"  placing post-only BUY {size} @ {price} on YES token "
                  f"(~${price * size:.2f}, deep — will not fill)")

    placed = await gw.place([Quote(meta.yes.token_id, Side.BUY, price, size)], meta)
    if not placed:
        console.print("  [red]✗ order not placed (see logs for the API error)[/red]")
        return False
    oid = placed[0].order_id
    console.print(f"  [green]✓[/green] placed — order id {oid[:16]}…")

    await asyncio.sleep(2.0)
    live = await gw.open_orders()
    found = any(o.order_id == oid for o in live)
    console.print(f"  [{'green' if found else 'yellow'}]{'✓' if found else '?'}[/] "
                  f"read back open orders: {len(live)} live, ours {'present' if found else 'not seen yet'}")

    await gw.cancel([oid])
    console.print("  [green]✓[/green] cancel sent")
    await asyncio.sleep(1.5)
    after = await gw.open_orders()
    still = any(o.order_id == oid for o in after)
    console.print(f"  [{'green' if not still else 'red'}]{'✓' if not still else '✗'}[/] "
                  f"order {'cancelled' if not still else 'STILL LIVE — cancel manually!'}")

    ok = bool(placed) and not still
    console.print(f"\n[bold]{'ROUND-TRIP OK' if ok else 'CHECK LOGS'}[/bold]")
    return ok
