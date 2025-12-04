"""Curve Finance connector for liquid staking token (LST) swaps.

Curve provides the best liquidity and lowest slippage for LST pairs like:
- stETH/ETH
- rETH/ETH (via rETH/wstETH pool)
- cbETH/ETH

Uses Curve's stable swap pools optimized for low-slippage swaps between
correlated assets.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict, cast

import structlog
from eth_typing import ChecksumAddress
from web3 import AsyncWeb3, Web3
from web3.contract import AsyncContract
from web3.types import TxParams, Wei

log = structlog.get_logger()

# Curve stETH/ETH pool (most liquid LST pool)
CURVE_STETH_POOL: ChecksumAddress = Web3.to_checksum_address(
    "0xDC24316b9AE028F1497c275EB9192a3Ea0f67022"
)

# Curve rETH/wstETH pool
CURVE_RETH_WSTETH_POOL: ChecksumAddress = Web3.to_checksum_address(
    "0x447Ddd4960d9fdBF6af9a790560d0AF76795CB08"
)

# Token addresses
STETH: ChecksumAddress = Web3.to_checksum_address(
    "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84"
)
WETH: ChecksumAddress = Web3.to_checksum_address(
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
)
RETH: ChecksumAddress = Web3.to_checksum_address(
    "0xae78736Cd615f374D3085123A210448E74Fc6393"
)
WSTETH: ChecksumAddress = Web3.to_checksum_address(
    "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"
)

# TypedDict for quote responses
class CurveQuote(TypedDict):
    expected_output: Decimal
    pool_address: ChecksumAddress
    pool_name: str
    coin_i: int
    coin_j: int
    amount_in_wei: int


class PoolInfo(TypedDict):
    contract: AsyncContract
    coin_i: int
    coin_j: int
    name: str


# Minimal ABI for Curve pools
CURVE_POOL_ABI = [
    {
        "name": "get_dy",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "i", "type": "int128"},
            {"name": "j", "type": "int128"},
            {"name": "dx", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "exchange",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "i", "type": "int128"},
            {"name": "j", "type": "int128"},
            {"name": "dx", "type": "uint256"},
            {"name": "min_dy", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "coins",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "arg0", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address"}],
    },
]


class CurveConnector:
    """Connector for Curve Finance LST pools."""

    def __init__(self, w3: AsyncWeb3, account_address: str) -> None:
        """Initialize Curve connector.

        Args:
            w3: AsyncWeb3 instance
            account_address: Address to execute swaps from
        """
        self.w3 = w3
        self.account_address: ChecksumAddress = Web3.to_checksum_address(
            account_address
        )

        # Initialize pool contracts with proper checksummed addresses
        self.steth_pool: AsyncContract = self.w3.eth.contract(
            address=CURVE_STETH_POOL, abi=CURVE_POOL_ABI
        )
        self.reth_wsteth_pool: AsyncContract = self.w3.eth.contract(
            address=CURVE_RETH_WSTETH_POOL, abi=CURVE_POOL_ABI
        )

        log.info(
            "curve.initialized",
            steth_pool=CURVE_STETH_POOL,
            reth_pool=CURVE_RETH_WSTETH_POOL,
        )

    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
    ) -> CurveQuote:
        """Get quote for LST swap via Curve.

        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap (in token decimals)

        Returns:
            Quote dict with expected_output and pool info

        Raises:
            ValueError: If no Curve pool supports the token pair
        """
        token_in_lower = token_in.lower()
        token_out_lower = token_out.lower()

        # Determine which pool and coin indices to use
        pool_info = self._get_pool_for_pair(token_in_lower, token_out_lower)
        if not pool_info:
            raise ValueError(
                f"No Curve pool found for {token_in_lower[:8]}.../{token_out_lower[:8]}..."
            )

        pool_contract = pool_info["contract"]
        coin_i = pool_info["coin_i"]
        coin_j = pool_info["coin_j"]

        # Convert amount to wei (assuming 18 decimals for LSTs)
        amount_in_wei = int(amount_in * Decimal(10**18))

        # Get quote from pool
        expected_out_wei = await pool_contract.functions.get_dy(
            coin_i, coin_j, amount_in_wei
        ).call()

        expected_output = Decimal(expected_out_wei) / Decimal(10**18)

        return CurveQuote(
            expected_output=expected_output,
            pool_address=pool_contract.address,
            pool_name=pool_info["name"],
            coin_i=coin_i,
            coin_j=coin_j,
            amount_in_wei=amount_in_wei,
        )

    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage_tolerance: Decimal = Decimal("0.005"),  # 50 bps
    ) -> TxParams:
        """Execute LST swap via Curve.

        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap
            slippage_tolerance: Maximum slippage (default 50 bps)

        Returns:
            Transaction parameters dict (ready for signing and sending)
        """
        # Get quote first
        quote = await self.get_quote(token_in, token_out, amount_in)

        # Calculate minimum output with slippage
        expected_output = quote["expected_output"]
        min_output = expected_output * (Decimal("1") - slippage_tolerance)
        min_output_wei = int(min_output * Decimal(10**18))

        pool_address = quote["pool_address"]
        pool_contract = (
            self.steth_pool
            if pool_address == CURVE_STETH_POOL
            else self.reth_wsteth_pool
        )

        # Get current fee data (EIP-1559)
        fee_history = await self.w3.eth.fee_history(1, "latest", [50])
        base_fee = fee_history["baseFeePerGas"][-1]
        priority_fee = fee_history["reward"][-1][0]

        # Build transaction with EIP-1559 fee model
        base_tx: TxParams = {
            "from": self.account_address,
            "gas": Wei(250_000),  # Curve swaps are gas-efficient
            "maxFeePerGas": Wei(base_fee * 2 + priority_fee),
            "maxPriorityFeePerGas": Wei(priority_fee),
        }

        tx_params: TxParams = await pool_contract.functions.exchange(
            quote["coin_i"],
            quote["coin_j"],
            quote["amount_in_wei"],
            min_output_wei,
        ).build_transaction(base_tx)

        log.info(
            "curve.swap_built",
            token_in=token_in[:10],
            token_out=token_out[:10],
            amount_in=float(amount_in),
            expected_output=float(expected_output),
            min_output=float(min_output),
            pool=quote["pool_name"],
        )

        return tx_params

    def _get_pool_for_pair(
        self, token_in: str, token_out: str
    ) -> PoolInfo | None:
        """Determine which Curve pool to use for a token pair.

        Args:
            token_in: Input token address (lowercase)
            token_out: Output token address (lowercase)

        Returns:
            Dict with contract, coin indices, and pool name, or None if unsupported
        """
        steth_lower = STETH.lower()
        weth_lower = WETH.lower()
        reth_lower = RETH.lower()
        wsteth_lower = WSTETH.lower()

        # stETH/ETH pool (most common)
        if (token_in == steth_lower and token_out == weth_lower) or (
            token_in == weth_lower and token_out == steth_lower
        ):
            return PoolInfo(
                contract=self.steth_pool,
                coin_i=1 if token_in == steth_lower else 0,  # ETH=0, stETH=1
                coin_j=0 if token_in == steth_lower else 1,
                name="stETH/ETH",
            )

        # rETH/wstETH pool (for rETH/ETH via wstETH bridge)
        if (token_in == reth_lower and token_out == wsteth_lower) or (
            token_in == wsteth_lower and token_out == reth_lower
        ):
            return PoolInfo(
                contract=self.reth_wsteth_pool,
                coin_i=0 if token_in == reth_lower else 1,  # rETH=0, wstETH=1
                coin_j=1 if token_in == reth_lower else 0,
                name="rETH/wstETH",
            )

        return None

    @staticmethod
    def supports_pair(token_in: str, token_out: str) -> bool:
        """Check if Curve supports this token pair.

        Args:
            token_in: Input token address
            token_out: Output token address

        Returns:
            True if the pair is supported, False otherwise
        """
        token_in_lower = token_in.lower()
        token_out_lower = token_out.lower()

        steth_lower = STETH.lower()
        weth_lower = WETH.lower()
        reth_lower = RETH.lower()
        wsteth_lower = WSTETH.lower()

        # stETH/ETH
        if (token_in_lower == steth_lower and token_out_lower == weth_lower) or (
            token_in_lower == weth_lower and token_out_lower == steth_lower
        ):
            return True

        # rETH/wstETH (can bridge to ETH)
        if (token_in_lower == reth_lower and token_out_lower == wsteth_lower) or (
            token_in_lower == wsteth_lower and token_out_lower == reth_lower
        ):
            return True

        return False
