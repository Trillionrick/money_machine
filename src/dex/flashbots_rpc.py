"""Flashbots RPC integration for MEV protection.

Provides private transaction submission to avoid frontrunning and sandwich attacks.
Uses Flashbots Protect API for submitting transactions privately.

2025 Production implementation with proper error handling and monitoring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3, Web3
from web3.types import TxParams, Wei

log = structlog.get_logger()


@dataclass
class FlashbotsConfig:
    """Configuration for Flashbots integration."""

    # Flashbots RPC endpoint
    relay_url: str = "https://relay.flashbots.net"

    # Flashbots Protect RPC (for simple transactions)
    protect_rpc_url: str = "https://rpc.flashbots.net"

    # Bundle simulation
    enable_simulation: bool = True

    # Retry settings
    max_blocks_wait: int = 25  # Wait up to 25 blocks (~5 minutes)
    retry_delay_seconds: float = 12.0  # One block time

    # Monitoring
    track_bundle_stats: bool = True


@dataclass
class FlashbotsBundleStats:
    """Statistics for Flashbots bundle submissions."""

    bundles_sent: int = 0
    bundles_included: int = 0
    bundles_failed: int = 0
    bundles_timeout: int = 0
    total_gas_saved_gwei: float = 0.0
    avg_inclusion_blocks: float = 0.0


class FlashbotsRPC:
    """Flashbots RPC client for private transaction submission.

    Provides two modes:
    1. Protect RPC: Simple private transaction submission (recommended for most cases)
    2. Bundle submission: Advanced bundle construction for complex MEV strategies
    """

    def __init__(
        self,
        web3: AsyncWeb3,
        signer: LocalAccount,
        config: FlashbotsConfig | None = None,
    ):
        """Initialize Flashbots RPC client.

        Args:
            web3: Web3 instance connected to Ethereum
            signer: Account for signing Flashbots requests
            config: Flashbots configuration
        """
        self.web3 = web3
        self.signer = signer
        self.config = config or FlashbotsConfig()
        self.stats = FlashbotsBundleStats()

        self.log = structlog.get_logger()

        # HTTP client for Flashbots API
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_private_transaction(
        self,
        transaction: TxParams,
        max_block_number: int | None = None,
    ) -> str:
        """Send a transaction privately via Flashbots Protect.

        This is the recommended method for most use cases. The transaction
        will not be visible in the public mempool and is protected from
        frontrunning.

        Args:
            transaction: Transaction parameters
            max_block_number: Optional max block number for inclusion

        Returns:
            Transaction hash

        Raises:
            Exception: If submission fails
        """
        self.log.info(
            "flashbots.sending_private_tx",
            to=transaction.get("to"),
            value=transaction.get("value"),
        )

        try:
            # Send via Flashbots Protect RPC
            # This is a simple JSON-RPC call that protects the transaction
            tx_params = dict(transaction)

            # Sign the transaction
            signed = self.web3.eth.account.sign_transaction(
                tx_params,
                private_key=self.signer.key,
            )

            # Submit to Flashbots Protect
            tx_hash = await self._submit_to_protect_rpc(signed.raw_transaction)

            self.log.info("flashbots.private_tx_sent", tx_hash=tx_hash)

            return tx_hash

        except Exception as e:
            self.log.exception("flashbots.private_tx_failed", error=str(e))
            raise

    async def _submit_to_protect_rpc(self, raw_tx: bytes) -> str:
        """Submit transaction to Flashbots Protect RPC.

        Args:
            raw_tx: Signed raw transaction bytes

        Returns:
            Transaction hash
        """
        # Create a Web3 instance connected to Flashbots Protect RPC
        flashbots_web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.protect_rpc_url))

        # Send the transaction
        tx_hash = await flashbots_web3.eth.send_raw_transaction(raw_tx)

        return Web3.to_hex(tx_hash)

    async def send_bundle(
        self,
        transactions: list[TxParams],
        target_block: int | None = None,
    ) -> dict[str, Any]:
        """Send a bundle of transactions via Flashbots.

        This is for advanced use cases where you need to submit multiple
        transactions atomically (e.g., complex arbitrage with multiple steps).

        Args:
            transactions: List of transactions to bundle
            target_block: Target block number (uses next block if None)

        Returns:
            Bundle submission result

        Raises:
            Exception: If bundle submission fails
        """
        if target_block is None:
            current_block = await self.web3.eth.block_number
            target_block = current_block + 1

        self.log.info(
            "flashbots.sending_bundle",
            tx_count=len(transactions),
            target_block=target_block,
        )

        try:
            # Sign all transactions
            signed_txs = []
            for tx in transactions:
                signed = self.web3.eth.account.sign_transaction(
                    tx,
                    private_key=self.signer.key,
                )
                signed_txs.append(Web3.to_hex(signed.raw_transaction))

            # Simulate bundle if enabled
            if self.config.enable_simulation:
                sim_result = await self._simulate_bundle(signed_txs, target_block)
                if not sim_result.get("success"):
                    raise ValueError(f"Bundle simulation failed: {sim_result}")

            # Submit bundle
            result = await self._submit_bundle(signed_txs, target_block)

            self.stats.bundles_sent += 1

            self.log.info("flashbots.bundle_sent", result=result)

            return result

        except Exception as e:
            self.stats.bundles_failed += 1
            self.log.exception("flashbots.bundle_failed", error=str(e))
            raise

    async def _simulate_bundle(
        self,
        signed_transactions: list[str],
        target_block: int,
    ) -> dict[str, Any]:
        """Simulate bundle execution before submission.

        Args:
            signed_transactions: List of signed transaction hex strings
            target_block: Target block number

        Returns:
            Simulation result
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_callBundle",
            "params": [
                {
                    "txs": signed_transactions,
                    "blockNumber": hex(target_block),
                    "stateBlockNumber": "latest",
                }
            ],
        }

        # Sign the request
        headers = self._get_flashbots_headers(payload)

        response = await self.client.post(
            self.config.relay_url,
            json=payload,
            headers=headers,
        )

        response.raise_for_status()
        result = response.json()

        return result.get("result", {})

    async def _submit_bundle(
        self,
        signed_transactions: list[str],
        target_block: int,
    ) -> dict[str, Any]:
        """Submit bundle to Flashbots relay.

        Args:
            signed_transactions: List of signed transaction hex strings
            target_block: Target block number

        Returns:
            Submission result
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_sendBundle",
            "params": [
                {
                    "txs": signed_transactions,
                    "blockNumber": hex(target_block),
                }
            ],
        }

        # Sign the request
        headers = self._get_flashbots_headers(payload)

        response = await self.client.post(
            self.config.relay_url,
            json=payload,
            headers=headers,
        )

        response.raise_for_status()
        result = response.json()

        return result.get("result", {})

    def _get_flashbots_headers(self, payload: dict) -> dict[str, str]:
        """Generate Flashbots authentication headers.

        Args:
            payload: JSON-RPC payload

        Returns:
            Headers dict with X-Flashbots-Signature
        """
        import json
        from eth_account.messages import encode_defunct

        # Create signature message
        message = json.dumps(payload, separators=(",", ":"))
        message_hash = encode_defunct(text=message)

        # Sign with signer account
        signature = self.signer.sign_message(message_hash)

        return {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self.signer.address}:{signature.signature.hex()}",
        }

    async def wait_for_bundle_inclusion(
        self,
        bundle_hash: str,
        target_block: int,
    ) -> bool:
        """Wait for bundle to be included in a block.

        Args:
            bundle_hash: Bundle hash returned from submission
            target_block: Target block number

        Returns:
            True if included, False if timeout
        """
        max_wait_block = target_block + self.config.max_blocks_wait

        self.log.info(
            "flashbots.waiting_for_inclusion",
            bundle_hash=bundle_hash,
            target_block=target_block,
            max_block=max_wait_block,
        )

        while True:
            current_block = await self.web3.eth.block_number

            if current_block > max_wait_block:
                self.log.warning(
                    "flashbots.bundle_timeout",
                    bundle_hash=bundle_hash,
                    current_block=current_block,
                )
                self.stats.bundles_timeout += 1
                return False

            # Check bundle status
            status = await self._get_bundle_status(bundle_hash)

            if status.get("included"):
                self.log.info("flashbots.bundle_included", bundle_hash=bundle_hash)
                self.stats.bundles_included += 1

                # Update avg inclusion time
                blocks_waited = current_block - target_block
                self.stats.avg_inclusion_blocks = (
                    self.stats.avg_inclusion_blocks * (self.stats.bundles_included - 1)
                    + blocks_waited
                ) / self.stats.bundles_included

                return True

            # Wait for next block
            await asyncio.sleep(self.config.retry_delay_seconds)

    async def _get_bundle_status(self, bundle_hash: str) -> dict[str, Any]:
        """Get bundle inclusion status.

        Args:
            bundle_hash: Bundle hash

        Returns:
            Status dict
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "flashbots_getBundleStats",
            "params": [bundle_hash, "latest"],
        }

        headers = self._get_flashbots_headers(payload)

        try:
            response = await self.client.post(
                self.config.relay_url,
                json=payload,
                headers=headers,
            )

            response.raise_for_status()
            result = response.json()

            return result.get("result", {})

        except Exception as e:
            self.log.warning("flashbots.status_check_failed", error=str(e))
            return {}

    def get_stats(self) -> dict[str, Any]:
        """Get Flashbots usage statistics.

        Returns:
            Stats dict
        """
        inclusion_rate = (
            self.stats.bundles_included / self.stats.bundles_sent
            if self.stats.bundles_sent > 0
            else 0.0
        )

        return {
            "bundles_sent": self.stats.bundles_sent,
            "bundles_included": self.stats.bundles_included,
            "bundles_failed": self.stats.bundles_failed,
            "bundles_timeout": self.stats.bundles_timeout,
            "inclusion_rate": inclusion_rate,
            "avg_inclusion_blocks": self.stats.avg_inclusion_blocks,
            "total_gas_saved_gwei": self.stats.total_gas_saved_gwei,
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


def create_flashbots_rpc(
    rpc_url: str,
    private_key: str,
) -> FlashbotsRPC:
    """Create a Flashbots RPC client from environment.

    Args:
        rpc_url: Ethereum RPC URL
        private_key: Private key for signing (should be different from trading key)

    Returns:
        FlashbotsRPC instance
    """
    web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
    signer = Account.from_key(private_key)

    return FlashbotsRPC(web3, signer)
