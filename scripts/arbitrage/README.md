# Arbitrage Encoding Scripts

Modern Python implementation for encoding flash loan arbitrage parameters.

## Migration Notice

**DEPRECATED:** `encode_arb_data.js` (ethers.js v5)
**CURRENT:** `encode_arb_data.py` (web3.py v7, 2025 standard)

The JavaScript version has been replaced with a Python implementation that:
- ✅ Uses web3.py v7 (actively maintained, 2025 standard)
- ✅ Integrates with Money Machine's Python codebase
- ✅ Full type hints and async support
- ✅ Uses structlog for consistent logging
- ✅ Removes Node.js dependency
- ✅ Outputs both CLI and JSON formats

## Quick Start

### Installation

Ensure you have the required Python packages:

```bash
# From project root
pip install web3 eth-abi structlog
```

### Basic Usage

```bash
# Interactive mode with defaults
python scripts/arbitrage/encode_arb_data.py

# Custom parameters
python scripts/arbitrage/encode_arb_data.py \
    --borrow 100 \
    --min-profit 0.5 \
    --expected-profit 2 \
    --gas-price 50

# Specify contract address
export ARB_CONTRACT_ADDRESS=0xYourContractAddress
python scripts/arbitrage/encode_arb_data.py

# JSON output for automation
python scripts/arbitrage/encode_arb_data.py --json > params.json
```

### Command Line Options

```
--contract ADDRESS         Flash loan contract address (or ARB_CONTRACT_ADDRESS env var)
--borrow ETH              Borrow amount in ETH (default: 100)
--min-profit ETH          Minimum profit in ETH (default: 0.5)
--expected-profit ETH     Expected profit in ETH (default: 2)
--gas-estimate UNITS      Gas estimate in units (default: 350000)
--gas-price GWEI          Gas price in Gwei (default: 50)
--slippage BPS            Slippage tolerance in basis points (default: 50 = 0.5%)
--chain CHAIN             Target chain: ethereum or polygon (default: ethereum)
--json                    Output JSON instead of human-readable format
```

### Environment Variables

```bash
export ARB_CONTRACT_ADDRESS=0xYourContractAddress
export BORROW_AMOUNT=100
export MIN_PROFIT=0.5
export EXPECTED_PROFIT=2
export GAS_ESTIMATE=350000
export GAS_PRICE=50
```

## Output Formats

### Human-Readable (Default)

```
================================================================================
MONEY MACHINE - ARBITRAGE DATA ENCODER (Python)
================================================================================

✅ Contract Address: 0x1234...

📊 Configuration:
   Borrow Amount: 100 WETH
   Min Profit: 0.5 WETH
   Expected Profit: 2 WETH
   Gas Estimate: 350,000 units

💰 Profitability Analysis:
   Expected Gross Profit: 2 WETH
   Flash Loan Fee (0.05%): 0.050000 WETH
   Gas Cost (50 Gwei): 0.017500 ETH
   Net Profit: 1.932500 WETH
   ROI: 1.93%

📦 Encoded Data:
0x1234abcd...
```

### JSON Format

```bash
python scripts/arbitrage/encode_arb_data.py --json
```

```json
{
  "config": {
    "contract_address": "0x...",
    "borrow_amount_eth": "100",
    "min_profit_eth": "0.5",
    "expected_profit_eth": "2"
  },
  "encoded": {
    "swap_data": "0x...",
    "arb_data": "0x..."
  },
  "execution": {
    "loan_asset": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "loan_amount_wei": 100000000000000000000,
    "deadline": 1701234567
  },
  "analysis": {
    "net_profit_eth": "1.9325",
    "roi_bps": 193,
    "break_even_bps": 67
  },
  "safety": {
    "checks_passed": true,
    "warnings": []
  }
}
```

## Integration with Money Machine

The encoder integrates seamlessly with the existing codebase:

```python
from scripts.arbitrage.encode_arb_data import ArbitrageEncoder, ArbConfig

# Create configuration
config = ArbConfig(
    contract_address="0xYourContractAddress",
    borrow_amount_eth=Decimal("100"),
    min_profit_eth=Decimal("0.5"),
    expected_profit_eth=Decimal("2"),
    gas_estimate=350000,
)

# Encode data
encoder = ArbitrageEncoder(config)
result = encoder.encode()

# Use encoded data with FlashLoanExecutor
if result.checks_passed:
    # Execute via web3.py
    tx = contract.functions.requestFlashLoan(
        result.loan_asset,
        result.loan_amount_wei,
        bytes.fromhex(result.arb_data[2:])
    ).transact({'from': your_address, 'gas': 500000})
```

## Profitability Calculation

The encoder performs comprehensive profitability analysis:

1. **Flash Loan Fee** - Aave V3: 0.05% of borrowed amount
2. **Gas Cost** - Estimated gas units × gas price
3. **Slippage Cost** - Maximum slippage tolerance
4. **Net Profit** - Expected profit - all costs
5. **ROI** - Net profit / borrow amount (in basis points)
6. **Break-Even** - Minimum spread needed to cover costs

## Safety Checks

Pre-flight validation includes:

- ✅ Net profit is positive
- ✅ Net profit exceeds minimum threshold
- ✅ ROI > 1%
- ✅ Gas price is reasonable (≤ 100 Gwei)
- ✅ Contract address is configured
- ✅ Deadline is in the future

## Architecture

```
encode_arb_data.py
├── ArbConfig           # Configuration dataclass
├── EncodedArbData      # Output dataclass
└── ArbitrageEncoder    # Main encoder class
    ├── encode_swap_path()      # Uniswap V3 path encoding
    ├── encode_swap_data()      # exactInput calldata
    ├── encode_arb_data()       # ArbPlan struct
    ├── calculate_profitability()  # Cost analysis
    └── run_safety_checks()     # Validation
```

## Comparison: JavaScript vs Python

| Feature | encode_arb_data.js | encode_arb_data.py |
|---------|-------------------|-------------------|
| **Language** | JavaScript (Node.js) | Python 3.12+ |
| **Library** | ethers.js v5 (deprecated) | web3.py v7 (current) |
| **Type Safety** | ❌ No types | ✅ Full type hints |
| **Integration** | ❌ Separate runtime | ✅ Native Python |
| **Logging** | console.log | structlog |
| **Config** | Hardcoded | Uses TOKEN_ADDRESSES |
| **Async** | ❌ Callbacks | ✅ async/await |
| **JSON Output** | ❌ No | ✅ Yes |
| **Lines of Code** | 238 | 580 (with docs) |

## Migration Guide

If you were using the JavaScript version:

```bash
# Old way (JavaScript)
export ARB_CONTRACT_ADDRESS=0x...
node scripts/arbitrage/encode_arb_data.js

# New way (Python)
export ARB_CONTRACT_ADDRESS=0x...
python scripts/arbitrage/encode_arb_data.py
```

The Python version produces identical encoded data but with:
- Better error messages
- Comprehensive profitability analysis
- JSON output for automation
- Integration with existing Python infrastructure

## Testing

```bash
# Test with mock parameters
python scripts/arbitrage/encode_arb_data.py \
    --contract 0x1234567890123456789012345678901234567890 \
    --borrow 1 \
    --min-profit 0.01 \
    --expected-profit 0.02 \
    --json

# Validate output structure
python scripts/arbitrage/encode_arb_data.py --json | jq .
```

## Troubleshooting

**"Invalid contract address"**
- Set `ARB_CONTRACT_ADDRESS` environment variable
- Or use `--contract` flag with valid Ethereum address

**"Net profit is NEGATIVE"**
- Increase expected profit
- Lower gas price estimate
- Reduce slippage tolerance

**"Import error: No module named 'web3'"**
```bash
pip install web3 eth-abi structlog
```

## Next Steps

1. Deploy your flash loan contract
2. Set `ARB_CONTRACT_ADDRESS` environment variable
3. Run encoder to generate transaction data
4. Simulate transaction first (see `src/dex/flash_loan_executor.py`)
5. Execute on testnet
6. Monitor profitability and adjust parameters

## Support

Part of the Money Machine arbitrage system. For issues:
1. Check logs with `structlog` output
2. Verify token addresses in `src/dex/config.py`
3. Test on Sepolia/Mumbai testnet first
4. Review flash loan contract compatibility
