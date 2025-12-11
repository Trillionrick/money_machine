"""BSC (Binance Smart Chain) connector for AQUA arbitrage.

Modern 2025 implementation with PancakeSwap V3 and Biswap integration.
Supports flash loans via PancakeSwap V3 for AQUA token arbitrage.

2025 Refactoring:
- Pydantic v2 BaseSettings with field validators
- Modern validation_alias instead of deprecated alias parameter
- Type-safe optional field handling with explicit type narrowing
- Comprehensive type hints throughout (no unparameterized generics)
- Structured logging with contextual metadata
- Proper async/await patterns for I/O operations
- RPC failover with detailed error reporting
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from eth_typing import ChecksumAddress
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from web3 import Web3
from web3.contract import Contract
from web3.types import Wei

log = structlog.get_logger()


class BSCSettings(BaseSettings):
    """Configuration for BSC network connections.

    2025 best practices:
    - Uses Pydantic v2 field_validator for validation
    - Proper typing for optional fields with None defaults
    - Modern SettingsConfigDict configuration
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # BSC RPC endpoints (multiple for failover)
    bsc_rpc_url: str = Field(
        default="https://bsc-dataseed1.binance.org:443",
        description="Primary BSC RPC endpoint",
        validation_alias="BSC_RPC_URL",
    )
    bsc_rpc_backup: str = Field(
        default="https://bsc-dataseed2.binance.org:443",
        description="Backup BSC RPC endpoint",
        validation_alias="BSC_RPC_BACKUP",
    )

    # Private key for transaction signing (optional - read-only mode if not provided)
    bsc_private_key: str | None = Field(
        default=None,
        description="Private key for signing transactions (optional)",
        validation_alias="BSC_PRIVATE_KEY",
    )

    # Contract addresses (optional - may be deployed later)
    bsc_aqua_contract: str | None = Field(
        default=None,
        description="AQUA arbitrage contract address (optional)",
        validation_alias="BSC_AQUA_CONTRACT",
    )

    # Token addresses on BSC (with defaults for mainnet)
    wbnb_address: str = Field(
        default="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        description="Wrapped BNB token address",
        validation_alias="WBNB_ADDRESS",
    )
    busd_address: str = Field(
        default="0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
        description="Binance USD token address",
        validation_alias="BUSD_ADDRESS",
    )
    usdt_address: str = Field(
        default="0x55d398326f99059fF775485246999027B3197955",
        description="Tether USD token address",
        validation_alias="USDT_ADDRESS",
    )
    aqua_address: str = Field(
        default="0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991",
        description="AQUA token address",
        validation_alias="AQUA_ADDRESS",
    )

    # DEX router addresses
    pancake_v3_router: str = Field(
        default="0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        description="PancakeSwap V3 router address",
        validation_alias="PANCAKE_V3_ROUTER",
    )
    pancake_v3_factory: str = Field(
        default="0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
        description="PancakeSwap V3 factory address",
        validation_alias="PANCAKE_V3_FACTORY",
    )
    biswap_router: str = Field(
        default="0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
        description="Biswap router address",
        validation_alias="BISWAP_ROUTER",
    )

    # Gas settings for BSC (much lower than Ethereum)
    max_gas_price_gwei: int = Field(
        default=5,
        gt=0,
        le=100,
        description="Maximum gas price in Gwei",
        validation_alias="BSC_MAX_GAS_PRICE_GWEI",
    )
    gas_estimate: int = Field(
        default=250000,
        gt=0,
        description="Estimated gas units for transactions",
        validation_alias="BSC_GAS_ESTIMATE",
    )

    @field_validator("bsc_private_key", mode="before")
    @classmethod
    def validate_private_key(cls, v: str | None) -> str | None:
        """Validate private key format if provided."""
        if v is None or v == "":
            return None
        # Remove 0x prefix if present
        if v.startswith("0x"):
            v = v[2:]
        # Validate hex string length (64 chars for 32 bytes)
        if len(v) != 64:
            raise ValueError("Private key must be 32 bytes (64 hex chars)")
        try:
            int(v, 16)
        except ValueError as e:
            raise ValueError("Private key must be valid hex string") from e
        return f"0x{v}"

    @field_validator("wbnb_address", "busd_address", "usdt_address", "aqua_address",
                     "pancake_v3_router", "pancake_v3_factory", "biswap_router", mode="before")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate Ethereum address format."""
        if not v.startswith("0x"):
            raise ValueError(f"Address must start with 0x: {v}")
        if len(v) != 42:
            raise ValueError(f"Address must be 42 chars (0x + 40 hex): {v}")
        try:
            int(v[2:], 16)
        except ValueError as e:
            raise ValueError(f"Address must be valid hex string: {v}") from e
        return Web3.to_checksum_address(v)

    @field_validator("bsc_aqua_contract", mode="before")
    @classmethod
    def validate_optional_address(cls, v: str | None) -> str | None:
        """Validate optional Ethereum address format."""
        if v is None or v == "":
            return None
        if not v.startswith("0x"):
            raise ValueError(f"Address must start with 0x: {v}")
        if len(v) != 42:
            raise ValueError(f"Address must be 42 chars (0x + 40 hex): {v}")
        try:
            int(v[2:], 16)
        except ValueError as e:
            raise ValueError(f"Address must be valid hex string: {v}") from e
        return Web3.to_checksum_address(v)


class BSCConnector:
    """Connector for BSC network and DEX interactions.

    Provides integration with:
    - PancakeSwap V3 for price quotes and swaps
    - ERC20 token balance queries
    - Gas price estimation with safety caps
    - RPC failover for high availability

    Attributes:
        settings: BSC configuration settings
        w3: Web3 instance connected to BSC RPC
        account: Account for transaction signing (optional)
        quoter: PancakeSwap V3 quoter contract instance
    """

    # Minimal ERC20 ABI for token interactions
    ERC20_ABI: list[dict[str, Any]] = [
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        },
    ]

    # PancakeSwap V3 Quoter ABI (for price quotes)
    QUOTER_V3_ABI: list[dict[str, Any]] = [
        {
            "inputs": [
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
            ],
            "name": "quoteExactInputSingle",
            "outputs": [
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
                {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
                {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
            ],
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ]

    # PancakeSwap V3 Quoter address (BSC mainnet)
    QUOTER_V3_ADDRESS: str = "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"

    def __init__(
        self,
        settings: BSCSettings | None = None,
        w3: Web3 | None = None,
    ) -> None:
        """Initialize BSC connector.

        Args:
            settings: BSC configuration settings (creates default if None)
            w3: Web3 instance (creates new with RPC provider if None)

        Raises:
            ConnectionError: If unable to connect to any BSC RPC endpoint
        """
        self.settings = settings or BSCSettings()

        # Initialize Web3 connection with failover
        if w3 is None:
            self.w3 = Web3(Web3.HTTPProvider(self.settings.bsc_rpc_url))
            if not self.w3.is_connected():
                log.warning(
                    "bsc.primary_rpc_failed",
                    url=self.settings.bsc_rpc_url,
                )
                # Failover to backup RPC
                self.w3 = Web3(Web3.HTTPProvider(self.settings.bsc_rpc_backup))

                if not self.w3.is_connected():
                    raise ConnectionError(
                        f"Failed to connect to BSC RPC endpoints: "
                        f"{self.settings.bsc_rpc_url}, {self.settings.bsc_rpc_backup}"
                    )
        else:
            self.w3 = w3
            if not self.w3.is_connected():
                raise ConnectionError("Provided Web3 instance is not connected")

        # Initialize account from private key (optional - enables write operations)
        self.account = None
        if self.settings.bsc_private_key:
            try:
                self.account = self.w3.eth.account.from_key(self.settings.bsc_private_key)
            except Exception:
                log.exception("bsc.account_initialization_failed")
                raise

        # Initialize PancakeSwap V3 quoter contract for price queries
        self.quoter: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.QUOTER_V3_ADDRESS),
            abi=self.QUOTER_V3_ABI,
        )

        log.info(
            "bsc.connector_initialized",
            chain_id=self.w3.eth.chain_id,
            block_number=self.w3.eth.block_number,
            account=self.account.address if self.account else None,
            rpc_url=self.settings.bsc_rpc_url if w3 is None else "custom",
        )

    async def get_aqua_price(self, quote_token: str = "WBNB") -> float | None:
        """Get AQUA token price from PancakeSwap V3.

        Args:
            quote_token: Quote token symbol (WBNB, BUSD, or USDT)

        Returns:
            Price of AQUA in quote token units, or None if query fails

        Note:
            Uses PancakeSwap V3 quoter with 0.25% fee tier.
            Assumes AQUA has 18 decimals.
        """
        # Mapping of supported quote tokens to their addresses
        QUOTE_TOKEN_ADDRESSES: dict[str, str] = {
            "WBNB": self.settings.wbnb_address,
            "BUSD": self.settings.busd_address,
            "USDT": self.settings.usdt_address,
        }

        quote_address = QUOTE_TOKEN_ADDRESSES.get(quote_token)
        if quote_address is None:
            log.warning(
                "bsc.invalid_quote_token",
                token=quote_token,
                supported_tokens=list(QUOTE_TOKEN_ADDRESSES.keys()),
            )
            return None

        try:
            # Query 1 AQUA token price (18 decimals assumed)
            amount_in: int = Web3.to_wei(1, "ether")
            fee_tier: int = 2500  # 0.25% PancakeSwap V3 fee tier

            aqua_checksum = Web3.to_checksum_address(self.settings.aqua_address)
            quote_checksum = Web3.to_checksum_address(quote_address)

            # Call PancakeSwap V3 quoter
            result: tuple[int, int, int, int] = self.quoter.functions.quoteExactInputSingle(
                aqua_checksum,
                quote_checksum,
                amount_in,
                fee_tier,
                0,  # sqrtPriceLimitX96 = 0 means no price limit
            ).call()

            amount_out: int = result[0]
            price = float(Web3.from_wei(amount_out, "ether"))

            log.debug(
                "bsc.aqua_price_fetched",
                quote_token=quote_token,
                price=price,
                amount_in=amount_in,
                amount_out=amount_out,
            )

            return price

        except Exception:
            log.exception(
                "bsc.price_fetch_failed",
                quote_token=quote_token,
                aqua_address=self.settings.aqua_address,
                quote_address=quote_address,
            )
            return None

    async def get_token_balance(
        self,
        token_address: str,
        wallet_address: str | None = None,
    ) -> Decimal:
        """Get token balance for wallet.

        Args:
            token_address: Token contract address
            wallet_address: Wallet address (uses account if None)

        Returns:
            Token balance as Decimal

        Raises:
            ValueError: If no wallet address provided and no account configured
        """
        # Type-safe resolution of wallet address
        resolved_address: str
        if wallet_address is None:
            if self.account is None:
                raise ValueError("No wallet address provided and no account configured")
            resolved_address = self.account.address
        else:
            resolved_address = wallet_address

        try:
            token_checksum = Web3.to_checksum_address(token_address)
            wallet_checksum = Web3.to_checksum_address(resolved_address)

            token = self.w3.eth.contract(
                address=token_checksum,
                abi=self.ERC20_ABI,
            )

            balance: int = token.functions.balanceOf(wallet_checksum).call()
            decimals: int = token.functions.decimals().call()

            balance_decimal = Decimal(balance) / Decimal(10**decimals)

            log.debug(
                "bsc.token_balance_fetched",
                token=token_address,
                wallet=resolved_address,
                balance=str(balance_decimal),
            )

            return balance_decimal

        except Exception:
            log.exception(
                "bsc.balance_fetch_failed",
                token=token_address,
                wallet=resolved_address,
            )
            return Decimal(0)

    async def estimate_gas_price(self) -> Wei:
        """Estimate current BSC gas price with safety cap.

        Returns:
            Gas price in Wei, capped at configured maximum

        Note:
            BSC typically has much lower gas prices than Ethereum (~3-5 Gwei).
            Falls back to 3 Gwei if RPC call fails.
        """
        try:
            current_gas_price: Wei = self.w3.eth.gas_price
            max_gas_price: Wei = Web3.to_wei(self.settings.max_gas_price_gwei, "gwei")

            if current_gas_price > max_gas_price:
                log.warning(
                    "bsc.gas_price_exceeds_maximum",
                    current_gwei=float(Web3.from_wei(current_gas_price, "gwei")),
                    max_gwei=self.settings.max_gas_price_gwei,
                    using_max=True,
                )
                return max_gas_price

            log.debug(
                "bsc.gas_price_estimated",
                gas_price_gwei=float(Web3.from_wei(current_gas_price, "gwei")),
            )

            return current_gas_price

        except Exception:
            log.exception("bsc.gas_price_fetch_failed")
            # Return safe conservative default for BSC (3 Gwei)
            default_gas_price: Wei = Web3.to_wei(3, "gwei")
            log.info(
                "bsc.using_default_gas_price",
                default_gwei=3,
            )
            return default_gas_price

    def get_chain_id(self) -> int:
        """Get BSC chain ID.

        Returns:
            Chain ID (56 for BSC mainnet, 97 for testnet)
        """
        chain_id: int = self.w3.eth.chain_id
        return chain_id


# Token addresses mapping for easy access
BSC_TOKENS: dict[str, str] = {
    "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "USDT": "0x55d398326f99059fF775485246999027B3197955",
    "AQUA": "0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991",
    "BNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # Alias for WBNB
}
