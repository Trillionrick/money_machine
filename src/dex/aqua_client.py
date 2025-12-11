"""Minimal Aqua Protocol client for encoding calls and parsing events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from eth_typing import ChecksumAddress, HexStr
from web3 import AsyncWeb3, Web3
from web3.contract.contract import ContractEvent


AQUA_CONTRACT_ADDRESSES: dict[int, str] = {
    1: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Ethereum
    56: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # BNB
    137: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Polygon
    42161: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Arbitrum
    43114: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Avalanche
    100: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Gnosis
    8453: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Base
    10: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Optimism
    324: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # zkSync
    59144: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Linea
    1301: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Unichain
    146: "0x499943e74fb0ce105688beee8ef2abec5d936d31",  # Sonic
}


ABI: list[dict[str, Any]] = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "maker", "type": "address"},
            {"indexed": False, "name": "app", "type": "address"},
            {"indexed": False, "name": "strategyHash", "type": "bytes32"},
            {"indexed": False, "name": "token", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"},
        ],
        "name": "Pushed",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "maker", "type": "address"},
            {"indexed": False, "name": "app", "type": "address"},
            {"indexed": False, "name": "strategyHash", "type": "bytes32"},
            {"indexed": False, "name": "token", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"},
        ],
        "name": "Pulled",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "maker", "type": "address"},
            {"indexed": False, "name": "app", "type": "address"},
            {"indexed": False, "name": "strategyHash", "type": "bytes32"},
        ],
        "name": "Shipped",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "maker", "type": "address"},
            {"indexed": False, "name": "app", "type": "address"},
            {"indexed": False, "name": "strategyHash", "type": "bytes32"},
        ],
        "name": "Docked",
        "type": "event",
    },
    {
        "inputs": [
            {"name": "app", "type": "address"},
            {"name": "strategy", "type": "bytes"},
            {
                "components": [
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                ],
                "name": "amountsAndTokens",
                "type": "tuple[]",
            },
        ],
        "name": "ship",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "app", "type": "address"},
            {"name": "strategyHash", "type": "bytes32"},
            {"name": "tokens", "type": "address[]"},
        ],
        "name": "dock",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass
class AquaEvent:
    """Parsed Aqua event."""

    name: str
    maker: str
    app: str
    strategy_hash: str
    token: str | None = None
    amount: int | None = None
    tx_hash: str | None = None
    block_number: int | None = None
    chain_id: int | None = None


class AquaClient:
    """Lightweight Aqua contract helper."""

    def __init__(self, w3: Web3 | AsyncWeb3, chain_id: int):
        self.w3 = w3
        self.chain_id = chain_id
        self.address = Web3.to_checksum_address(AQUA_CONTRACT_ADDRESSES[chain_id])
        self.contract = self.w3.eth.contract(address=self.address, abi=ABI)

    def build_ship(self, app: str, strategy: HexStr, amounts_and_tokens: list[dict[str, Any]]) -> dict[str, Any]:
        """Build ship tx dict (to, data, value)."""
        fn = self.contract.functions.ship(app, strategy, amounts_and_tokens)
        return {
            "to": self.address,
            "data": fn._encode_transaction_data(),  # type: ignore[attr-defined]
            "value": 0,
        }

    def build_dock(self, app: str, strategy_hash: HexStr, tokens: Iterable[str]) -> dict[str, Any]:
        """Build dock tx dict."""
        fn = self.contract.functions.dock(app, strategy_hash, list(tokens))
        return {
            "to": self.address,
            "data": fn._encode_transaction_data(),  # type: ignore[attr-defined]
            "value": 0,
        }

    def parse_event(self, log: dict[str, Any]) -> AquaEvent | None:
        """Parse a raw log into AquaEvent, or None if unrelated."""
        for ev in ("Pushed", "Pulled", "Shipped", "Docked"):
            try:
                decoded = getattr(self.contract.events, ev)().process_log(log)
                args = decoded["args"]
                return AquaEvent(
                    name=ev,
                    maker=str(args.get("maker")),
                    app=str(args.get("app")),
                    strategy_hash=args.get("strategyHash"),
                    token=str(args.get("token")) if "token" in args else None,
                    amount=int(args.get("amount")) if "amount" in args else None,
                    tx_hash=decoded["transactionHash"].hex(),
                    block_number=decoded.get("blockNumber"),
                    chain_id=self.chain_id,
                )
            except Exception:
                continue
        return None

    def get_event_signatures(self) -> list[HexStr]:
        """Return topic0 signatures for Aqua events."""
        topics: list[HexStr] = []
        for ev_name in ("Pushed", "Pulled", "Shipped", "Docked"):
            event_abi = self.contract.events[ev_name]().abi  # type: ignore[index]
            inputs = event_abi.get("inputs", [])
            signature_hash = Web3.keccak(text=f"{ev_name}({','.join(i['type'] for i in inputs)})").hex()
            topics.append(HexStr(signature_hash))  # type: ignore[call-overload]
        return topics
