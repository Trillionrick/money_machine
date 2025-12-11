"""Async Web3 connector for Uniswap V3 SwapRouter interactions."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog
from eth_account import Account
import httpx
from web3 import AsyncHTTPProvider, AsyncWeb3
# Import specific types required for web3.py
from web3.types import TxParams, Nonce, _Hash32, HexBytes, Wei # type: ignore

logger = structlog.get_logger()


class UniswapWeb3Connector:
    """Async Web3 helper for approvals, swaps, and receipt handling."""

    ROUTER_ABI = [
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "address", "name": "tokenIn", "type": "address"},
                        {"internalType": "address", "name": "tokenOut", "type": "address"},
                        {"internalType": "uint24", "name": "fee", "type": "uint24"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                        {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                    ],
                    "internalType": "struct IV3SwapRouter.ExactInputSingleParams",
                    "name": "params",
                    "type": "tuple",
                }
            ],
            "name": "exactInputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function",
        }
    ]

    ERC20_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "spender", "type": "address"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    def __init__(
        self,
        rpc_url: str,
        router_address: str,
        private_key: str | None = None,
        private_relays: list[str] | None = None,
        private_relay_timeout: int = 20,
        enable_private_cancel: bool = False,
        private_relay_tip_bump_pct: float = 15.0,
    ):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.router_address = self.w3.to_checksum_address(router_address)
        self.router = self.w3.eth.contract(address=self.router_address, abi=self.ROUTER_ABI)

        self.private_relays = [r for r in (private_relays or []) if r]
        self.private_relay_timeout = private_relay_timeout
        self.enable_private_cancel = enable_private_cancel
        self.private_relay_tip_bump_factor = 1 + max(0.0, private_relay_tip_bump_pct) / 100.0

        if private_key:
            self.account = Account.from_key(private_key)
        else:
            self.account = None

    async def get_token_balance(self, token_address: str, wallet_address: str) -> int:
        """Return ERC20 token balance for wallet."""
        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token_address),
            abi=self.ERC20_ABI,
        )
        balance = await token_contract.functions.balanceOf(
            self.w3.to_checksum_address(wallet_address)
        ).call()
        return balance

    async def approve_token(self, token_address: str, spender_address: str, amount: int) -> str:
        """Approve token spending by spender."""
        if self.account is None:
            msg = "Private key required for token approvals"
            raise ValueError(msg)

        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token_address),
            abi=self.ERC20_ABI,
        )

        # FIX: Define tx as TxParams to satisfy type checker.
        tx_params: TxParams = {
            "from": self.account.address,
            # FIX: Explicitly cast the transaction count to Nonce type.
            "nonce": cast(Nonce, await self.w3.eth.get_transaction_count(self.account.address)),
            "gas": 100000,
            # FIX: Explicitly cast gas prices to the expected Wei type.
            "maxFeePerGas": cast(Wei, await self.w3.eth.gas_price),
            "maxPriorityFeePerGas": self.w3.to_wei(2, "gwei"),
        }

        tx = await token_contract.functions.approve(
            self.w3.to_checksum_address(spender_address),
            amount,
        ).build_transaction(tx_params)

        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        logger.info(
            "dex.token_approval_submitted",
            token=token_address,
            tx_hash=tx_hash.hex(),
        )
        return tx_hash.hex()

    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        amount_out_min: int,
        fee_tier: int = 3000,
        recipient: str | None = None,
    ) -> str:
        """Execute exact input swap on Uniswap V3."""
        if self.account is None:
            msg = "Private key required for swaps"
            raise ValueError(msg)

        resolved_recipient = recipient or self.account.address
        swap_params = {
            "tokenIn": self.w3.to_checksum_address(token_in),
            "tokenOut": self.w3.to_checksum_address(token_out),
            "fee": fee_tier,
            "recipient": self.w3.to_checksum_address(resolved_recipient),
            "amountIn": amount_in,
            "amountOutMinimum": amount_out_min,
            "sqrtPriceLimitX96": 0,
        }

        base_gas_price = await self.w3.eth.gas_price
        # Ensure bumped_gas_price is treated as Wei/int, though web3.py expects a numeric type that matches Wei
        bumped_gas_price = int(base_gas_price * self.private_relay_tip_bump_factor)

        # FIX: Define tx as TxParams to satisfy type checker.
        tx_params: TxParams = {
            "from": self.account.address,
            # FIX: Explicitly cast the transaction count to Nonce type.
            "nonce": cast(Nonce, await self.w3.eth.get_transaction_count(self.account.address)),
            "gas": 300000,
            # FIX: Explicitly cast gas prices to the expected Wei type.
            "maxFeePerGas": cast(Wei, bumped_gas_price),
            "maxPriorityFeePerGas": cast(Wei, int(self.w3.to_wei(2, "gwei") * self.private_relay_tip_bump_factor)),
        }

        tx = await self.router.functions.exactInputSingle(swap_params).build_transaction(
            tx_params
        )

        signed_tx = self.account.sign_transaction(tx)
        tx_hash_hex = signed_tx.hash.hex()
        sent_private = False
        if self.private_relays:
            for relay in self.private_relays:
                ok = await self._send_private_raw_transaction(relay, signed_tx.raw_transaction, tx_hash_hex)
                sent_private = sent_private or ok
            if sent_private:
                receipt = await self._wait_for_receipt_with_timeout(tx_hash_hex, self.private_relay_timeout)
                if receipt:
                    logger.info(
                        "dex.swap_executed_private",
                        token_in=token_in,
                        token_out=token_out,
                        amount_in=amount_in,
                        tx_hash=tx_hash_hex,
                    )
                    return tx_hash_hex
                logger.info(
                    "dex.private_relay_timeout_resend",
                    tx_hash=tx_hash_hex,
                    timeout_sec=self.private_relay_timeout,
                )

        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        logger.info(
            "dex.swap_executed",
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            tx_hash=tx_hash_hex,
            path="public" if not sent_private else "private+public_fallback",
        )

        if self.enable_private_cancel:
            receipt = await self._wait_for_receipt_with_timeout(tx_hash_hex, self.private_relay_timeout)
            if receipt:
                return tx_hash_hex
            
            # FIX: Use .get() for optional key access in TypedDict and cast to int.
            cancel_hash = await self._send_cancel_transaction(cast(int, tx.get("nonce")))
            if cancel_hash:
                logger.info("dex.swap_cancel_submitted", tx_hash=cancel_hash)

        return tx_hash_hex

    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> dict:
        """Wait for transaction confirmation and return receipt."""
        # FIX: Convert the hex string to HexBytes (or _Hash32) before passing it to the function.
        tx_hash_bytes = cast(_Hash32, HexBytes(tx_hash))
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=timeout)
        return dict(receipt)

    async def _send_private_raw_transaction(self, relay_url: str, raw_tx: bytes, tx_hash: str) -> bool:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction", "params": [raw_tx.hex()]}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(relay_url, json=payload)
                response.raise_for_status()
                data = response.json()
                if data.get("error"):
                    logger.warning("dex.private_relay_error", error=data["error"], relay=relay_url)
                    return False
                logger.info("dex.private_relay_sent", tx_hash=tx_hash, relay=relay_url)
                return True
        except Exception:
            logger.debug("dex.private_relay_failed", tx_hash=tx_hash, relay=relay_url)
            return False

    async def _wait_for_receipt_with_timeout(self, tx_hash: str, timeout: int) -> dict | None:
        try:
            return await self.wait_for_transaction(tx_hash, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    async def _send_cancel_transaction(self, nonce: int) -> str | None:
        if self.account is None:
            return None
        try:
            gas_price = await self.w3.eth.gas_price
            bump = int(gas_price * 1.2)
            # FIX: Define tx as TxParams to satisfy type checker (though it's a dict literal here).
            tx: TxParams = {
                "from": self.account.address,
                "to": self.account.address,
                "value": 0, # type: ignore
                # Nonce is an int here due to the function signature
                "nonce": cast(Nonce, nonce),
                "gas": 30000,
                "maxFeePerGas": cast(Wei, bump),
                "maxPriorityFeePerGas": self.w3.to_wei(3, "gwei"),
            }
            signed = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
            return tx_hash.hex()
        except Exception:
            logger.debug("dex.cancel_tx_failed")
            return None