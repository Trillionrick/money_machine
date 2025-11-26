"""Async Web3 connector for Uniswap V3 SwapRouter interactions."""

from __future__ import annotations

from typing import Dict, Optional

import structlog
from eth_account import Account
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.middleware import SignAndSendRawMiddlewareBuilder

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
        private_key: Optional[str] = None,
    ):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.router_address = self.w3.to_checksum_address(router_address)
        self.router = self.w3.eth.contract(address=self.router_address, abi=self.ROUTER_ABI)

        if private_key:
            self.account = Account.from_key(private_key)
            self.w3.middleware_onion.inject(
                SignAndSendRawMiddlewareBuilder.build(private_key),
                layer=0,
            )
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

        tx = await token_contract.functions.approve(
            self.w3.to_checksum_address(spender_address),
            amount,
        ).build_transaction(
            {
                "from": self.account.address,
                "nonce": await self.w3.eth.get_transaction_count(self.account.address),
                "gas": 100000,
                "maxFeePerGas": await self.w3.eth.gas_price,
                "maxPriorityFeePerGas": self.w3.to_wei(2, "gwei"),
            }
        )

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
        recipient: Optional[str] = None,
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

        tx = await self.router.functions.exactInputSingle(swap_params).build_transaction(
            {
                "from": self.account.address,
                "nonce": await self.w3.eth.get_transaction_count(self.account.address),
                "gas": 300000,
                "maxFeePerGas": await self.w3.eth.gas_price,
                "maxPriorityFeePerGas": self.w3.to_wei(2, "gwei"),
            }
        )

        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        logger.info(
            "dex.swap_executed",
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            tx_hash=tx_hash.hex(),
        )

        return tx_hash.hex()

    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> Dict:
        """Wait for transaction confirmation and return receipt."""
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return dict(receipt)
