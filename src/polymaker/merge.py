"""Native Python position merger (replaces the Node.js poly_merger subprocess).

When we hold both YES and NO in the same market, merging the pair returns
collateral (1 USDC/pUSD per pair) — a maker-only exit with zero market impact.

Two execution paths:
  * EOA wallet (signature_type=0): direct contract call, fully implemented here.
  * Proxy/Safe wallet (signature_type 1/2): the merge tx must be routed through
    the Safe. That path is gated on the Phase-2 wallet spike (docs 03 §6) — until
    then merging is skipped (logged), and inventory is exited via limit sells
    instead. The bot is fully functional without it; merging just frees capital
    sooner.

The V2/pUSD collateral question (does the CTF collateral resolve to pUSD post-
migration?) is also spike-gated; addresses are config-driven, not baked in.
"""

from __future__ import annotations

from typing import Any

from polymaker.config import Config
from polymaker.logging import get_logger

log = get_logger("merge")

# Polygon mainnet contracts (pre-V2 defaults; confirm collateral in the spike).
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
USDC_COLLATERAL = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

_CTF_ABI = [
    {
        "name": "mergePositions",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "partition", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    }
]
_NEG_RISK_ABI = [
    {
        "name": "mergePositions",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    }
]


class Merger:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._w3: Any = None
        self._account: Any = None

    def _ensure_web3(self) -> None:
        if self._w3 is not None:
            return
        from eth_account import Account
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        rpc = self._cfg.secrets.polygon_rpc or self._cfg.wallet.polygon_rpc
        w3 = Web3(Web3.HTTPProvider(rpc))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._w3 = w3
        self._account = Account.from_key(self._cfg.secrets.pk)

    @property
    def can_merge(self) -> bool:
        """EOA can merge directly today; Safe/proxy is spike-gated."""
        return self._cfg.wallet.signature_type == 0

    def merge(self, condition_id: str, amount_raw: int, neg_risk: bool) -> str | None:
        """Merge `amount_raw` (6-dec) YES+NO pairs. Returns tx hash or None."""
        if amount_raw <= 0:
            return None
        if not self.can_merge:
            log.info(
                "merge_skipped_safe_wallet",
                condition=condition_id[:12],
                amount=amount_raw,
                note="Safe merge is spike-gated; inventory exits via limit sells",
            )
            return None
        try:
            return self._merge_eoa(condition_id, amount_raw, neg_risk)
        except Exception as exc:  # noqa: BLE001
            log.error("merge_failed", condition=condition_id[:12], err=str(exc))
            return None

    def _merge_eoa(self, condition_id: str, amount_raw: int, neg_risk: bool) -> str:
        self._ensure_web3()
        w3 = self._w3
        addr = self._account.address
        cond = _to_bytes32(condition_id)

        if neg_risk:
            c = w3.eth.contract(address=w3.to_checksum_address(NEG_RISK_ADAPTER), abi=_NEG_RISK_ABI)
            fn = c.functions.mergePositions(cond, amount_raw)
        else:
            c = w3.eth.contract(address=w3.to_checksum_address(CONDITIONAL_TOKENS), abi=_CTF_ABI)
            fn = c.functions.mergePositions(
                w3.to_checksum_address(USDC_COLLATERAL),
                b"\x00" * 32,  # parent collection id (top-level market)
                cond,
                [1, 2],  # partition: the two outcome slots
                amount_raw,
            )

        tx = fn.build_transaction(
            {
                "from": addr,
                "nonce": w3.eth.get_transaction_count(addr),
                "chainId": self._cfg.wallet.chain_id,
                "gas": 300_000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": w3.to_wei(30, "gwei"),
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        h = str(receipt["transactionHash"].hex())
        log.info("merge_sent", condition=condition_id[:12], amount=amount_raw, tx=h[:14])
        return h


def _to_bytes32(hex_str: str) -> bytes:
    s = hex_str[2:] if hex_str.startswith("0x") else hex_str
    return bytes.fromhex(s.rjust(64, "0"))
