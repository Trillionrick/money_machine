"""
Live blockchain activity monitor - 2025 implementation.

Shows real-time on-chain events: NFT transfers, DEX swaps, wallet activity.
Designed for compact dashboard integration with minimal overhead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import structlog
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.types import FilterParams, LogReceipt

log = structlog.get_logger()


# Event signatures
NFT_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


@dataclass
class BlockchainEvent:
    """Real-time blockchain event."""

    event_type: str  # "nft_transfer", "swap", "token_transfer", "new_block"
    chain: str
    block_number: int
    tx_hash: str | None
    timestamp: str
    summary: str  # Human-readable summary
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)


class LiveBlockchainMonitor:
    """Lightweight real-time blockchain monitor."""

    def __init__(
        self,
        rpc_url: str,
        chain_name: str,
        watched_wallets: list[str] | None = None,
        nft_contracts: list[str] | None = None,
        dex_contracts: list[str] | None = None,
        on_event: Callable[[BlockchainEvent], Awaitable[None]] | None = None,
    ):
        """
        Initialize monitor.

        Args:
            rpc_url: RPC endpoint URL
            chain_name: Chain name for display
            watched_wallets: Wallets to monitor (optional)
            nft_contracts: NFT contracts to monitor (uses popular ones if None)
            dex_contracts: DEX pools to monitor (uses popular ones if None)
            on_event: Async callback for events
        """
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.chain_name = chain_name
        self.watched_wallets = watched_wallets or []
        self.on_event = on_event
        self.last_block = 0
        self.running = False
        self.event_count = 0

        # Default to monitoring popular contracts
        self.nft_contracts = nft_contracts or self._get_default_nfts()
        self.dex_contracts = dex_contracts or self._get_default_dex()

    def _get_default_nfts(self) -> list[str]:
        """Get popular NFT contracts to monitor."""
        if self.chain_name == "ethereum":
            return [
                "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D",  # BAYC
                "0x60E4d786628Fea6478F785A6d7e704777c86a7c6",  # MAYC
                "0xED5AF388653567Af2F388E6224dC7C4b3241C544",  # Azuki
            ]
        elif self.chain_name == "polygon":
            return ["0x2953399124F0cBB46d2CbACD8A89cF0599974963"]
        return []

    def _get_default_dex(self) -> list[str]:
        """Get popular DEX pools to monitor."""
        if self.chain_name == "ethereum":
            return [
                "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",  # USDC/ETH
                "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",  # USDC/ETH 0.3%
            ]
        elif self.chain_name == "polygon":
            return ["0x55CAaBB0d2b704FD0eF8192A7E35D8837e678207"]
        return []

    async def start(self) -> None:
        """Start monitoring."""
        try:
            self.last_block = await self.w3.eth.block_number
            self.running = True
            log.info(
                "blockchain_monitor.started",
                chain=self.chain_name,
                block=self.last_block,
            )
        except Exception as e:
            log.error("blockchain_monitor.start_failed", chain=self.chain_name, error=str(e))
            self.last_block = 0
            self.running = False

    async def stop(self) -> None:
        """Stop monitoring."""
        self.running = False
        log.info(
            "blockchain_monitor.stopped",
            chain=self.chain_name,
            events=self.event_count,
        )

    async def poll_once(self) -> None:
        """Poll for new events (single iteration)."""
        if not self.running:
            return

        try:
            current_block = await self.w3.eth.block_number

            if current_block <= self.last_block:
                return

            # Scan limited range to avoid RPC throttling
            from_block = max(self.last_block, current_block - 5)

            # Emit block update
            await self._emit(BlockchainEvent(
                event_type="new_block",
                chain=self.chain_name,
                block_number=current_block,
                tx_hash=None,
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary=f"Block {current_block:,}",
                data={"height": current_block},
            ))

            # Scan for NFT activity
            if self.nft_contracts:
                await self._scan_nfts(from_block, current_block)

            # Scan for DEX activity
            if self.dex_contracts:
                await self._scan_swaps(from_block, current_block)

            self.last_block = current_block

        except Exception as e:
            log.debug("blockchain_monitor.poll_error", error=str(e))

    async def _scan_nfts(self, from_block: int, to_block: int) -> None:
        """Scan for NFT transfers."""
        try:
            logs = await self.w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": [self.w3.to_checksum_address(a) for a in self.nft_contracts],
                "topics": [NFT_TRANSFER_TOPIC],
            })

            for log_entry in logs[:3]:  # Limit to 3 most recent
                await self._parse_nft_transfer(log_entry)

        except Exception:
            pass

    async def _scan_swaps(self, from_block: int, to_block: int) -> None:
        """Scan for DEX swaps."""
        try:
            logs = await self.w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": [self.w3.to_checksum_address(a) for a in self.dex_contracts],
                "topics": [UNISWAP_V3_SWAP_TOPIC],
            })

            for log_entry in logs[:2]:  # Limit to 2 most recent
                await self._parse_swap(log_entry)

        except Exception:
            pass

    async def _parse_nft_transfer(self, log_entry: LogReceipt) -> None:
        """Parse NFT transfer event."""
        try:
            if len(log_entry["topics"]) < 4:
                return

            token_id = int(log_entry["topics"][3].hex(), 16)
            to_addr = "0x" + log_entry["topics"][2].hex()[-40:]

            await self._emit(BlockchainEvent(
                event_type="nft_transfer",
                chain=self.chain_name,
                block_number=log_entry["blockNumber"],
                tx_hash=log_entry["transactionHash"].hex(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary=f"NFT #{token_id} → {to_addr[:6]}...{to_addr[-4:]}",
                data={
                    "contract": log_entry["address"],
                    "token_id": token_id,
                    "to": to_addr,
                    "tx": log_entry["transactionHash"].hex(),
                },
            ))

        except Exception:
            pass

    async def _parse_swap(self, log_entry: LogReceipt) -> None:
        """Parse DEX swap event."""
        try:
            await self._emit(BlockchainEvent(
                event_type="swap",
                chain=self.chain_name,
                block_number=log_entry["blockNumber"],
                tx_hash=log_entry["transactionHash"].hex(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary=f"Swap on {log_entry['address'][:8]}...{log_entry['address'][-4:]}",
                data={
                    "pool": log_entry["address"],
                    "tx": log_entry["transactionHash"].hex(),
                },
            ))

        except Exception:
            pass

    async def _emit(self, event: BlockchainEvent) -> None:
        """Emit event via callback."""
        self.event_count += 1

        if self.on_event:
            try:
                await self.on_event(event)
            except Exception as e:
                log.debug("event_callback.error", error=str(e))

    async def run(self) -> None:
        """Run monitor loop."""
        await self.start()

        try:
            while self.running:
                await self.poll_once()
                await asyncio.sleep(3.0)  # Poll every 3 seconds
        finally:
            await self.stop()


async def create_monitor(
    chain: str,
    rpc_url: str,
    wallets: list[str] | None = None,
    on_event: Callable[[BlockchainEvent], Awaitable[None]] | None = None,
) -> LiveBlockchainMonitor:
    """
    Factory function to create a blockchain monitor.

    Args:
        chain: Chain name ("ethereum" or "polygon")
        rpc_url: RPC endpoint
        wallets: Optional wallet addresses to monitor
        on_event: Event callback

    Returns:
        Configured monitor instance
    """
    return LiveBlockchainMonitor(
        rpc_url=rpc_url,
        chain_name=chain,
        watched_wallets=wallets,
        on_event=on_event,
    )
