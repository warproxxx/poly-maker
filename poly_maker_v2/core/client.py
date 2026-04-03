"""
PolymarketClient: async-friendly wrapper around py_clob_client.

Key design decisions vs the reference repo:
  - All blocking SDK calls (sign, HTTP) run in run_in_executor() so they
    never block the asyncio event loop.
  - Returns raw dicts/lists instead of pandas DataFrames — DataFrames are
    only used in the reconciler, which is off the hot path.
  - No Google Sheets dependency.
  - Constructor takes a Config object, not raw env vars.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

import requests
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    OrderArgs,
    PartialCreateOrderOptions,
    OpenOrderParams,
)
from py_clob_client.constants import POLYGON

from core.abis import erc20_abi, NegRiskAdapterABI, ConditionalTokenABI, ADDRESSES

logger = logging.getLogger(__name__)


class PolymarketClient:
    """
    Wraps py_clob_client and Polygon Web3.
    All async methods are safe to await from the event loop.
    """

    def __init__(self, config: Any) -> None:
        """
        Args:
            config: Config dataclass from config_loader.py
        """
        self.browser_wallet = Web3.to_checksum_address(config.browser_address)

        logger.info("Initialising Polymarket client for %s", self.browser_wallet)

        # ── CLOB client (signing + REST) ───────────────────────────────────
        self._clob = ClobClient(
            host=config.api_host,
            key=config.private_key,
            chain_id=POLYGON,
            funder=self.browser_wallet,
            signature_type=2,   # EIP-191
        )
        self._creds = self._clob.create_or_derive_api_creds()
        self._clob.set_api_creds(creds=self._creds)

        # ── Web3 / Polygon ─────────────────────────────────────────────────
        w3 = Web3(Web3.HTTPProvider(config.polygon_rpc_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._w3 = w3

        self._usdc = w3.eth.contract(
            address=ADDRESSES["collateral_usdc"],
            abi=erc20_abi,
        )
        self._conditional_tokens = w3.eth.contract(
            address=ADDRESSES["conditional_tokens"],
            abi=ConditionalTokenABI,
        )
        self._neg_risk_adapter = w3.eth.contract(
            address=ADDRESSES["neg_risk_adapter"],
            abi=NegRiskAdapterABI,
        )

    # ── Credentials (for WS auth) ──────────────────────────────────────────

    def get_api_creds(self) -> dict:
        """Return API credentials dict for WebSocket authentication."""
        return {
            "apiKey": self._creds.api_key,
            "secret": self._creds.api_secret,
            "passphrase": self._creds.api_passphrase,
        }

    # ── Order management ───────────────────────────────────────────────────

    async def post_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        neg_risk: bool = False,
    ) -> dict:
        """
        Sign and submit a limit order. Runs signing + HTTP in a thread
        so the event loop is never blocked.

        Args:
            token_id: The outcome token ID to trade.
            side:     "BUY" or "SELL"
            price:    Limit price in [0, 1]
            size:     Order size in USDC
            neg_risk: True for NegRisk markets.

        Returns:
            Raw API response dict, or {} on error.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(self._sync_post_order, token_id, side, price, size, neg_risk),
        )

    def _sync_post_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        neg_risk: bool,
    ) -> dict:
        order_args = OrderArgs(
            token_id=str(token_id),
            price=price,
            size=size,
            side=side,
        )
        if neg_risk:
            signed = self._clob.create_order(
                order_args, options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed = self._clob.create_order(order_args)
        try:
            resp = self._clob.post_order(signed)
            return resp
        except Exception as exc:
            logger.error("post_order failed token=%s side=%s price=%s: %s", token_id, side, price, exc)
            return {}

    async def cancel_token_orders(self, token_id: str) -> None:
        """Cancel all open orders for a specific outcome token."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(self._clob.cancel_market_orders, asset_id=str(token_id)),
        )

    async def cancel_market_orders(self, condition_id: str) -> None:
        """Cancel all open orders across both tokens of a market."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(self._clob.cancel_market_orders, market=condition_id),
        )

    async def cancel_all_orders(self) -> None:
        """Cancel every open order in the account."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._clob.cancel_all)

    # ── Order / position queries ────────────────────────────────────────────

    async def get_open_orders(self) -> list[dict]:
        """Fetch all open orders as a list of raw dicts."""
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._clob.get_orders)
        return raw or []

    async def get_market_open_orders(self, condition_id: str) -> list[dict]:
        """Fetch open orders for a specific market."""
        loop = asyncio.get_running_loop()
        params = OpenOrderParams(market=condition_id)
        raw = await loop.run_in_executor(
            None, partial(self._clob.get_orders, params)
        )
        return raw or []

    async def get_all_positions(self) -> list[dict]:
        """
        Fetch all positions from the Polymarket data API.
        Returns a list of position dicts (assetId, size, avgPrice, ...).
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get_positions)

    def _sync_get_positions(self) -> list[dict]:
        url = f"https://data-api.polymarket.com/positions?user={self.browser_wallet}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json() or []
        except Exception as exc:
            logger.error("get_all_positions failed: %s", exc)
            return []

    # ── Balance queries ─────────────────────────────────────────────────────

    async def get_usdc_balance(self) -> float:
        """Return USDC balance of the browser wallet."""
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            partial(self._usdc.functions.balanceOf(self.browser_wallet).call),
        )
        return raw / 1e6

    async def get_position_value(self) -> float:
        """Return total value of all open positions (from data API)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get_pos_value)

    def _sync_get_pos_value(self) -> float:
        url = f"https://data-api.polymarket.com/value?user={self.browser_wallet}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return float(resp.json().get("value", 0))
        except Exception as exc:
            logger.error("get_position_value failed: %s", exc)
            return 0.0

    async def get_total_balance(self) -> float:
        """USDC balance + position value."""
        usdc, pos = await asyncio.gather(self.get_usdc_balance(), self.get_position_value())
        return usdc + pos

    # ── On-chain token balance (for merge amount calculation) ───────────────

    def get_raw_token_balance(self, token_id: int) -> int:
        """
        Synchronous on-chain balanceOf call.
        Only used at startup/reconcile — not in the hot path.
        """
        return int(
            self._conditional_tokens.functions.balanceOf(
                self.browser_wallet, int(token_id)
            ).call()
        )
