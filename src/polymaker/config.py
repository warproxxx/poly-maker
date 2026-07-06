"""Configuration: pydantic models over local TOML files + .env secrets.

Replaces the v1 Google Sheets config entirely. Three files under config/:
  config.toml    engine/wallet/risk/execution settings
  strategy.toml  named parameter profiles
  markets.toml   the trade list (market -> profile + overrides)

Secrets (private key, wallet address) come only from the environment / .env.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WalletConfig(BaseModel):
    chain_id: int = 137
    signature_type: int = 2
    clob_host: str = "https://clob.polymarket.com"
    gamma_host: str = "https://gamma-api.polymarket.com"
    data_api_host: str = "https://data-api.polymarket.com"
    polygon_rpc: str = "https://polygon-bor-rpc.publicnode.com"


class EngineConfig(BaseModel):
    debounce_ms: int = 200
    # baseline periodic re-quote (book reactions are event-driven & instant; this
    # is just a slow refresh for cool-off re-entry / exit-urgency updates). A
    # precise wake is also scheduled for the exact moment an EVENT cool-off ends.
    quoter_tick_s: float = 60.0
    reconcile_interval_s: float = 30.0
    catalog_refresh_s: float = 900.0
    heartbeat: bool = True
    heartbeat_interval_s: float = 5.0
    journal: bool = True
    loop: str = "uvloop"


class RiskConfig(BaseModel):
    max_total_exposure_usdc: float = 5000.0
    max_event_group_loss_usdc: float = 1000.0
    max_market_notional_usdc: float = 800.0
    daily_loss_kill_usdc: float = 250.0
    ws_stale_halt_s: float = 10.0
    # user WS down this long -> we can't see our fills -> pull all quotes
    user_ws_blind_halt_s: float = 15.0
    # consecutive heartbeat failures -> exchange is auto-cancelling us -> halt
    heartbeat_halt_failures: int = 3
    max_order_error_rate: float = 0.25


class ExecutionConfig(BaseModel):
    rate_budget_fraction: float = 0.25
    post_only: bool = True
    max_orders_per_batch: int = 15


class PathsConfig(BaseModel):
    db: str = "state.db"
    journal_dir: str = "journal"
    log_dir: str = "logs"


class StrategyProfile(BaseModel):
    """One named parameter set. Every knob the quoter uses lives here."""

    model_config = ConfigDict(extra="forbid")

    # fair value
    micro_levels: int = 3
    flow_ewma_halflife_s: float = 120.0
    # spread / skew
    gamma: float = 0.5
    delta_min_ticks: int = 2
    c_vol: float = 1.2
    c_tox: float = 2.0
    # vol horizons
    vol_short_halflife_s: float = 10.0
    vol_long_halflife_s: float = 900.0
    # sizing / inventory
    base_size_usdc: float = 50.0
    q_max_usdc: float = 500.0
    q_soft_frac: float = 0.6
    layers: int = 2
    layer_step_ticks: int = 2
    # multiplier on the market's reward min-size that reward-eligible orders are
    # bumped to (margin above the scoring floor). 1.5 => 100-share min -> 150.
    reward_size_mult: float = 1.0
    # placement / churn
    reprice_ticks: int = 2
    resize_frac: float = 0.15
    min_edge_ticks: int = 1
    # regime
    event_cooloff_s: float = 60.0
    event_jump_ticks: int = 8
    event_sweep_levels: int = 3
    # sweep = a print >= event_sweep_mult order-sizes AND >= event_sweep_frac of
    # the near-touch depth it consumed (both must hold to flag a toxic sweep)
    event_sweep_mult: float = 4.0
    event_sweep_frac: float = 0.8
    trend_flow_z: float = 1.5
    # short/long realized-vol ratio that trips TRENDING (half size). On a thin
    # book microprice jitter inflates this without real trade flow, so raise it
    # for reward-farming markets that trade rarely.
    trend_vol_ratio: float = 2.0
    # lifecycle
    end_date_taper_days: float = 7.0
    reduce_only_hours: float = 24.0
    halt_before_hours: float = 2.0
    # exits
    exit_urgency_s: float = 900.0
    merge_min_size: float = 20.0

    def with_overrides(self, overrides: dict[str, Any]) -> StrategyProfile:
        """Return a copy with per-market override values applied."""
        if not overrides:
            return self
        data = self.model_dump()
        for k, v in overrides.items():
            if k in data:
                data[k] = v
        return StrategyProfile(**data)


# Keys allowed on a market entry that are NOT profile overrides.
_MARKET_RESERVED = {"slug", "condition_id", "profile", "enabled"}


class MarketEntry(BaseModel):
    """One line of the trade list. Extra keys are treated as profile overrides."""

    model_config = ConfigDict(extra="allow")

    slug: str | None = None
    condition_id: str | None = None
    profile: str = "political-longdated"
    enabled: bool = True

    @model_validator(mode="after")
    def _need_identifier(self) -> MarketEntry:
        if not self.slug and not self.condition_id:
            raise ValueError("market entry needs a slug or condition_id")
        return self

    @property
    def overrides(self) -> dict[str, Any]:
        extra = self.model_extra or {}
        return {k: v for k, v in extra.items() if k not in _MARKET_RESERVED}

    @property
    def ref(self) -> str:
        return self.slug or self.condition_id or "?"


class Secrets(BaseSettings):
    """Loaded from environment / .env. Never written to disk by us."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    pk: str = Field(default="", alias="PK")
    browser_address: str = Field(default="", alias="BROWSER_ADDRESS")
    polygon_rpc: str | None = Field(default=None, alias="POLYGON_RPC")
    alert_webhook_url: str | None = Field(default=None, alias="ALERT_WEBHOOK_URL")

    @property
    def has_wallet(self) -> bool:
        return bool(self.pk and self.browser_address)


class Config(BaseModel):
    """Fully-resolved configuration tree."""

    wallet: WalletConfig = WalletConfig()
    engine: EngineConfig = EngineConfig()
    risk: RiskConfig = RiskConfig()
    execution: ExecutionConfig = ExecutionConfig()
    paths: PathsConfig = PathsConfig()
    profiles: dict[str, StrategyProfile] = {}
    markets: list[MarketEntry] = []
    secrets: Secrets = Field(default_factory=Secrets)
    config_dir: Path = Path("config")

    @property
    def proxy(self) -> str | None:
        # Standard proxy env var; ALL_PROXY lets you route through an SSH tunnel
        # (e.g. simulate colocation during local testing). httpx and web3 honor
        # it automatically once load_dotenv() has run.
        return os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY")

    @property
    def enabled_markets(self) -> list[MarketEntry]:
        return [m for m in self.markets if m.enabled]

    def profile_for(self, entry: MarketEntry) -> StrategyProfile:
        base = self.profiles.get(entry.profile)
        if base is None:
            raise KeyError(f"unknown strategy profile: {entry.profile!r}")
        return base.with_overrides(entry.overrides)

    @classmethod
    def load(cls, config_dir: str | Path = "config", *, load_env: bool = True) -> Config:
        cdir = Path(config_dir)
        if load_env:
            load_dotenv()
        main = _read_toml(cdir / "config.toml")
        strat = _read_toml(cdir / "strategy.toml")
        mkts = _read_toml(cdir / "markets.toml")

        profiles = {
            name: StrategyProfile(**params)
            for name, params in (strat.get("profiles") or {}).items()
        }
        markets = [MarketEntry(**m) for m in (mkts.get("markets") or [])]

        return cls(
            wallet=WalletConfig(**main.get("wallet", {})),
            engine=EngineConfig(**main.get("engine", {})),
            risk=RiskConfig(**main.get("risk", {})),
            execution=ExecutionConfig(**main.get("execution", {})),
            paths=PathsConfig(**main.get("paths", {})),
            profiles=profiles,
            markets=markets,
            secrets=Secrets(),
            config_dir=cdir,
        )

    def reload_markets(self) -> Config:
        """Re-read markets.toml only (used by the hot-reload path)."""
        mkts = _read_toml(self.config_dir / "markets.toml")
        self.markets = [MarketEntry(**m) for m in (mkts.get("markets") or [])]
        return self


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)
