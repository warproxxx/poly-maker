"""
Config loader: reads .env and YAML config files into a single validated Config object.

Usage:
    from config_loader import Config
    config = Config.load()
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


# ── Sub-configs ────────────────────────────────────────────────────────────────

@dataclass
class ExecutionConfig:
    rate_limit_per_second: int = 10
    rate_limit_per_minute: int = 200
    order_epsilon_price: float = 0.005    # skip reprice if diff < this (in probability units)
    order_epsilon_size_pct: float = 0.10  # skip resize if diff < 10%


@dataclass
class MarketsConfig:
    market_intervals: list[int] = field(default_factory=lambda: [5, 15])
    market_tags: list[str] = field(default_factory=lambda: ["crypto"])
    max_active_markets: int = 50
    market_poll_interval_seconds: int = 30
    min_merge_size_usdc: float = 20.0
    merge_check_on_expiry: bool = True
    expiry_warning_seconds: int = 45
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)


# ── Root config ────────────────────────────────────────────────────────────────

@dataclass
class Config:
    # ── From .env ────────────────────────────────────────────────────────────
    private_key: str
    browser_address: str
    polygon_rpc_url: str

    # ── From config/markets.yaml ─────────────────────────────────────────────
    markets: MarketsConfig

    # ── From config/strategy.yaml ────────────────────────────────────────────
    # Passed through as-is to the strategy constructor; user-defined schema.
    strategy_params: dict

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, env_file: str = ".env", config_dir: str = "config") -> "Config":
        """
        Load and validate configuration.

        Args:
            env_file:   path to the .env file (relative to cwd or absolute)
            config_dir: directory containing markets.yaml and strategy.yaml
        """
        # 1. Load .env
        load_dotenv(dotenv_path=env_file)

        private_key = os.getenv("PK", "")
        browser_address = os.getenv("BROWSER_ADDRESS", "")
        polygon_rpc_url = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")

        _require("PK", private_key)
        _require("BROWSER_ADDRESS", browser_address)

        # 2. Load markets.yaml
        markets_path = Path(config_dir) / "markets.yaml"
        markets_raw = _load_yaml(markets_path)
        markets_cfg = _parse_markets(markets_raw)

        # 3. Load strategy.yaml
        strategy_path = Path(config_dir) / "strategy.yaml"
        strategy_params = _load_yaml(strategy_path)

        return cls(
            private_key=private_key,
            browser_address=browser_address,
            polygon_rpc_url=polygon_rpc_url,
            markets=markets_cfg,
            strategy_params=strategy_params,
        )

    @property
    def api_host(self) -> str:
        return "https://clob.polymarket.com"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"Required environment variable '{name}' is not set. Check your .env file.")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def _parse_markets(raw: dict) -> MarketsConfig:
    exec_raw = raw.get("execution", {})
    execution = ExecutionConfig(
        rate_limit_per_second=exec_raw.get("rate_limit_per_second", 10),
        rate_limit_per_minute=exec_raw.get("rate_limit_per_minute", 200),
        order_epsilon_price=exec_raw.get("order_epsilon_price", 0.005),
        order_epsilon_size_pct=exec_raw.get("order_epsilon_size_pct", 0.10),
    )
    return MarketsConfig(
        market_intervals=raw.get("market_intervals", [5, 15]),
        market_tags=raw.get("market_tags", ["crypto"]),
        max_active_markets=raw.get("max_active_markets", 50),
        market_poll_interval_seconds=raw.get("market_poll_interval_seconds", 30),
        min_merge_size_usdc=raw.get("min_merge_size_usdc", 20.0),
        merge_check_on_expiry=raw.get("merge_check_on_expiry", True),
        expiry_warning_seconds=raw.get("expiry_warning_seconds", 45),
        execution=execution,
    )
