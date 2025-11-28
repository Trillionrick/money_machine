# Flash Loan Arbitrage - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Step 1: Deploy Contract (Remix)

1. Go to https://remix.ethereum.org
2. Create `EnhancedHighSpeedArbRunner.sol` from `contracts/`
3. Compile with Solidity 0.8.25
4. Deploy with:
   - `_aavePool`: `0x87870Bca3f5FD6335c3f4d4C530Eed06fb5de523`
   - `_uniV3Router`: `0xE592427A0AEce92De3Edee1F18E0157C05861564`
   - `_weth`: `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2`
5. **Copy the deployed address!**

### Step 2: Configure Environment

```bash
# .env
ARB_CONTRACT_ADDRESS=0xYourDeployedAddress
ETH_RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY
PRIVATE_KEY=your_private_key
MAX_GAS_PRICE_GWEI=100
MIN_PROFIT_THRESHOLD_ETH=0.5
```

### Step 3: Install Dependencies

```bash
pip install web3 eth-typing
```

### Step 4: Test Connection

```python
from src.dex.flash_loan_executor import FlashLoanExecutor
executor = FlashLoanExecutor()
print(f"✅ Connected: {executor.account.address}")
```

### Step 5: Find Opportunities

```python
from decimal import Decimal
from src.dex.price_comparator import PriceComparator, PriceQuote

comparator = PriceComparator()

quotes = [
    PriceQuote("Uniswap", "ETH/USDC", Decimal("3000"), Decimal("5000000")),
    PriceQuote("SushiSwap", "ETH/USDC", Decimal("3030"), Decimal("2000000")),
]

opportunity = comparator.analyze_opportunity(quotes)
if opportunity:
    print(comparator.format_opportunity(opportunity))
```

### Step 6: Run Scanner (Dry-Run)

```python
from src.live.flash_arb_runner import FlashArbConfig, FlashArbitrageRunner

config = FlashArbConfig(
    enable_flash_loans=True,
    enable_execution=False,  # DRY RUN
    min_edge_bps=25.0,
    flash_loan_threshold_bps=100.0
)

# Use your existing router, dex, price_fetcher
runner = FlashArbitrageRunner(
    router=your_router,
    dex=your_dex,
    price_fetcher=your_price_fetcher,
    token_addresses={"ETH": "0xC02a...", "USDC": "0xA0b8..."},
    config=config
)

await runner.run(["ETH/USDC"])
```

---

## 📊 What You Get

✅ **Smart Contract** - Flash loan arbitrage on Ethereum
✅ **Python Integration** - Works with your existing system
✅ **Price Scanner** - Automatic opportunity detection
✅ **Risk Management** - Profitability checks before execution
✅ **Subgraph Tracking** - Monitor all trades
✅ **Documentation** - Complete guides

---

## 🎯 Key Files

| File | Purpose |
|------|---------|
| `contracts/EnhancedHighSpeedArbRunner.sol` | Smart contract |
| `src/dex/flash_loan_executor.py` | Python Web3 integration |
| `src/live/flash_arb_runner.py` | Enhanced scanner |
| `src/dex/price_comparator.py` | Find opportunities |
| `scripts/arbitrage/encode_arb_data.js` | JavaScript encoder |
| `documentation/arbitrage/FLASH_LOAN_ARBITRAGE_GUIDE.md` | Full guide |

---

## 💡 Example: Execute an Arbitrage

```python
from web3 import Web3
from src.dex.flash_loan_executor import FlashLoanExecutor

# Initialize
executor = FlashLoanExecutor()

# Build plan (WETH/USDC circular arbitrage)
plan = executor.build_weth_usdc_arb_plan(
    borrow_amount_eth=50,     # Borrow 50 ETH
    expected_profit_eth=1.0,   # Expect 1 ETH profit
    min_profit_eth=0.3         # Minimum 0.3 ETH required
)

# Check profitability
profitability = executor.calculate_profitability(
    borrow_amount=Web3.to_wei(50, "ether"),
    expected_profit=Web3.to_wei(1.0, "ether")
)

print(f"Net Profit: {Web3.from_wei(profitability.net_profit, 'ether')} ETH")
print(f"ROI: {profitability.roi_bps / 100}%")
print(f"Profitable: {profitability.is_profitable}")

# Execute (if profitable)
if profitability.is_profitable:
    receipt = executor.execute_flash_loan(
        loan_asset=executor.settings.weth_address,
        loan_amount=Web3.to_wei(50, "ether"),
        arb_plan=plan,
        dry_run=False  # Set True for testing
    )

    if receipt and receipt['status'] == 1:
        print(f"✅ Success! TX: {receipt['transactionHash'].hex()}")
```

---

## ⚠️ Safety First

**Before Mainnet:**
1. ✅ Test on Sepolia testnet
2. ✅ Run in dry-run mode
3. ✅ Start with small amounts
4. ✅ Monitor gas prices
5. ✅ Verify profitability

**Red Flags:**
- ❌ Gas > 100 Gwei
- ❌ Spread < 0.5%
- ❌ Low liquidity
- ❌ Unverified prices

---

## 🆘 Troubleshooting

### "Contract address not set"
```bash
export ARB_CONTRACT_ADDRESS=0xYourActualAddress
```

### "Not profitable"
- Spread too small
- Gas too high
- Slippage too large

### "Insufficient liquidity"
- Pool too small for your trade size
- Reduce `borrow_amount_eth`

---

## 📚 Learn More

- **Full Guide**: `documentation/arbitrage/FLASH_LOAN_ARBITRAGE_GUIDE.md`
- **Contract**: `contracts/EnhancedHighSpeedArbRunner.sol`
- **Examples**: `tests/test_arbitrage_runner.py`

---

## 🎉 Ready to Go!

Your arbitrage system is set up. Start with dry-run mode and gradually scale up as you gain confidence.

**Happy Trading! 💰**
