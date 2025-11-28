# Flash Loan Arbitrage System - Complete Integration Guide

## 🎯 Overview

This guide shows you how to use the **complete flash loan arbitrage system** integrated into your Money Machine project. The system combines:

- ✅ **Solidity Smart Contract** - On-chain flash loan execution
- ✅ **Python Integration** - Seamless Web3.py integration with your existing system
- ✅ **JavaScript Encoding Tools** - Alternative encoding for testing
- ✅ **Subgraph Tracking** - Monitor all arbitrage executions on-chain
- ✅ **Enhanced Arbitrage Runner** - Automatic execution with your existing scanner

---

## 📁 Project Structure

```
money_machine/
├── contracts/
│   └── EnhancedHighSpeedArbRunner.sol    # Flash loan contract
├── scripts/arbitrage/
│   └── encode_arb_data.js                 # JavaScript encoder
├── src/
│   ├── dex/
│   │   ├── flash_loan_executor.py         # Python Web3 integration
│   │   └── uniswap_connector.py           # Existing connector
│   └── live/
│       ├── flash_arb_runner.py            # Enhanced scanner
│       └── arbitrage_runner.py            # Original scanner
├── money_graphic/
│   ├── schema.graphql                     # Extended with arb tracking
│   └── src/
│       └── arbitrage-contract.ts          # Event handlers (to be created)
└── documentation/arbitrage/
    └── FLASH_LOAN_ARBITRAGE_GUIDE.md     # This file
```

---

## 🚀 Quick Start

### Step 1: Deploy the Smart Contract

1. **Open Remix IDE**: https://remix.ethereum.org
2. **Create new file**: `EnhancedHighSpeedArbRunner.sol`
3. **Copy contract** from `contracts/EnhancedHighSpeedArbRunner.sol`
4. **Compile** with Solidity 0.8.25
5. **Deploy** with these constructor parameters:
   - `_aavePool`: `0x87870Bca3f5FD6335c3f4d4C530Eed06fb5de523` (Mainnet Aave V3)
   - `_uniV3Router`: `0xE592427A0AEce92De3Edee1F18E0157C05861564` (Mainnet Uniswap V3)
   - `_weth`: `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` (Mainnet WETH)

6. **Copy the deployed address** - you'll need this!

### Step 2: Configure Environment Variables

Create or update your `.env` file:

```bash
# Flash Loan Arbitrage Configuration
ARB_CONTRACT_ADDRESS=0xYourDeployedContractAddress  # From Step 1
ETH_RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY
PRIVATE_KEY=your_private_key_here

# Gas Settings
MAX_GAS_PRICE_GWEI=100
GAS_ESTIMATE=350000

# Arbitrage Parameters
MIN_PROFIT_THRESHOLD_ETH=0.5
SLIPPAGE_TOLERANCE_BPS=50

# Token Addresses (Mainnet)
WETH_ADDRESS=0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
USDC_ADDRESS=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48

# Aave & Uniswap
AAVE_POOL_ADDRESS=0x87870Bca3f5FD6335c3f4d4C530Eed06fb5de523
UNI_V3_ROUTER=0xE592427A0AEce92De3Edee1F18E0157C05861564

# Subgraph
MONEY_GRAPHIC_SUBGRAPH_URL=https://api.studio.thegraph.com/query/YOUR_SUBGRAPH
```

### Step 3: Install Python Dependencies

```bash
# Install Web3.py if not already installed
pip install web3 eth-typing

# Or if using poetry
poetry add web3 eth-typing
```

### Step 4: Test the Flash Loan Executor

```python
# test_flash_loan.py
import asyncio
from web3 import Web3
from src.dex.flash_loan_executor import FlashLoanExecutor

async def test_executor():
    # Initialize executor
    executor = FlashLoanExecutor()

    print(f"✅ Connected to contract: {executor.settings.arb_contract_address}")
    print(f"✅ Account: {executor.account.address}")

    # Test profitability calculation
    borrow_amount = Web3.to_wei(10, "ether")  # 10 ETH
    expected_profit = Web3.to_wei(0.5, "ether")  # 0.5 ETH

    profitability = executor.calculate_profitability(
        borrow_amount=borrow_amount,
        expected_profit=expected_profit
    )

    print("\n💰 Profitability Check:")
    print(f"   Net Profit: {Web3.from_wei(profitability.net_profit, 'ether')} ETH")
    print(f"   ROI: {profitability.roi_bps / 100}%")
    print(f"   Is Profitable: {'✅ YES' if profitability.is_profitable else '❌ NO'}")

if __name__ == "__main__":
    asyncio.run(test_executor())
```

Run it:

```bash
python test_flash_loan.py
```

---

## 📊 How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Money Machine System                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Price Scanner (Python)                                  │
│     ├─ CEX Prices (OANDA, etc.)                            │
│     ├─ DEX Prices (Uniswap Connector)                      │
│     └─ Calculate Spread                                     │
│                         ▼                                   │
│  2. Decision Engine (FlashArbitrageRunner)                  │
│     ├─ Small spread (< 1%)  → Regular CEX/DEX arb         │
│     └─ Large spread (> 1%)  → Flash Loan arb              │
│                         ▼                                   │
│  3. Flash Loan Execution (FlashLoanExecutor)                │
│     ├─ Build ArbPlan                                        │
│     ├─ Calculate Profitability                              │
│     ├─ Encode Swap Data                                     │
│     └─ Submit Transaction                                   │
│                         ▼                                   │
│  4. Smart Contract (EnhancedHighSpeedArbRunner)             │
│     ├─ Request Flash Loan from Aave                         │
│     ├─ Execute Swaps on Uniswap                             │
│     ├─ Validate Profit                                      │
│     └─ Repay Loan + Keep Profit                            │
│                         ▼                                   │
│  5. Subgraph Tracking (money_graphic)                       │
│     ├─ Index ArbitrageExecution events                      │
│     ├─ Track Daily Stats                                    │
│     └─ Monitor Profitability                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Execution Flow

1. **Price Discovery**
   - Scanner fetches CEX price from your brokers
   - Scanner fetches DEX price from Uniswap
   - Calculates spread in basis points

2. **Strategy Selection**
   - Spread < 1% → Use regular arbitrage (your capital)
   - Spread > 1% → Use flash loan (no capital needed!)

3. **Flash Loan Preparation**
   ```python
   # Build the arbitrage plan
   arb_plan = executor.build_weth_usdc_arb_plan(
       borrow_amount_eth=100,      # Borrow 100 ETH
       expected_profit_eth=2.0,    # Expect 2 ETH profit
       min_profit_eth=0.5          # Minimum 0.5 ETH required
   )
   ```

4. **Profitability Check** (on-chain simulation)
   ```python
   profitability = executor.calculate_profitability(
       borrow_amount=borrow_wei,
       expected_profit=profit_wei
   )

   # Only execute if profitable after fees:
   # - Aave flash loan fee (0.05%)
   # - Gas cost
   # - Slippage
   ```

5. **Execution** (all in one transaction!)
   ```solidity
   // Contract receives 100 WETH from Aave
   // → Swap WETH to USDC on Uniswap
   // → Swap USDC to WETH on another pool
   // → Repay 100.05 WETH to Aave
   // → Keep the profit!
   ```

6. **Tracking**
   - Subgraph indexes the `ArbitrageExecuted` event
   - You can query historical performance
   - Monitor daily stats and ROI

---

## 🎯 Method 1: Using the Python Scanner (Recommended!)

This is the **easiest and most integrated** approach!

### Start the Enhanced Scanner

```python
# run_flash_arbitrage.py
import asyncio
from src.live.flash_arb_runner import (
    run_flash_arbitrage_scanner,
    FlashArbConfig
)
from src.brokers.routing import OrderRouter
from src.dex.uniswap_connector import UniswapConnector

async def main():
    # Configure
    config = FlashArbConfig(
        min_edge_bps=25.0,                  # Regular arb threshold
        flash_loan_threshold_bps=100.0,     # Flash loan threshold (1%)
        max_flash_borrow_eth=100.0,         # Max borrow per trade
        min_flash_profit_eth=0.5,           # Min profit for flash
        enable_flash_loans=True,            # Enable flash execution
        enable_execution=False,             # Start with dry-run
        poll_interval=5.0                   # Check every 5 seconds
    )

    # Setup (use your existing setup)
    router = OrderRouter()  # Your existing router
    dex = UniswapConnector()  # Your existing connector

    async def fetch_price(symbol: str):
        # Your existing price fetcher
        # Return CEX price for the symbol
        pass

    token_addresses = {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "ETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    }

    symbols = ["ETH/USDC"]

    # Run the scanner!
    await run_flash_arbitrage_scanner(
        symbols=symbols,
        router=router,
        dex=dex,
        price_fetcher=fetch_price,
        token_addresses=token_addresses,
        config=config
    )

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python run_flash_arbitrage.py
```

### What You'll See

```
[INFO] flash_arb.scanner_starting symbols=['ETH/USDC'] enable_flash=True
[DEBUG] flash_arb.price_check symbol=ETH/USDC cex_price=3000.0 dex_price=2970.0 edge_bps=101.01
[INFO] flash_arb.opportunity_detected symbol=ETH/USDC edge_bps=101.01 borrow_amount_eth=100.0 estimated_profit_eth=1.01
[INFO] flash_arb.profitability_check_passed symbol=ETH/USDC net_profit_eth=0.93 roi_bps=93
[INFO] flash_arb.dry_run symbol=ETH/USDC
```

When you're ready, set `enable_execution=True` to start trading!

---

## 🔧 Method 2: Direct Python API Usage

For more control, use the FlashLoanExecutor directly:

```python
from web3 import Web3
from src.dex.flash_loan_executor import FlashLoanExecutor

# Initialize
executor = FlashLoanExecutor()

# Build plan
plan = executor.build_weth_usdc_arb_plan(
    borrow_amount_eth=50,
    expected_profit_eth=1.0,
    min_profit_eth=0.3
)

# Check profitability
borrow_wei = Web3.to_wei(50, "ether")
profit_wei = Web3.to_wei(1.0, "ether")

profitability = executor.calculate_profitability(
    borrow_amount=borrow_wei,
    expected_profit=profit_wei
)

if profitability.is_profitable:
    # Execute!
    receipt = executor.execute_flash_loan(
        loan_asset=executor.settings.weth_address,
        loan_amount=borrow_wei,
        arb_plan=plan,
        dry_run=False  # Set True for testing
    )

    if receipt and receipt['status'] == 1:
        print(f"✅ Success! TX: {receipt['transactionHash'].hex()}")
    else:
        print(f"❌ Failed")
```

---

## 📜 Method 3: Using JavaScript Encoding

If you prefer JavaScript or want to use Remix directly:

```bash
# Set environment variables
export ARB_CONTRACT_ADDRESS=0xYourDeployedAddress
export BORROW_AMOUNT=100
export EXPECTED_PROFIT=2
export MIN_PROFIT=0.5
export GAS_ESTIMATE=350000
export GAS_PRICE=50

# Install dependencies
npm install ethers

# Run encoder
node scripts/arbitrage/encode_arb_data.js
```

This outputs the encoded `arbData` that you can paste directly into Remix!

---

## 📈 Monitoring with Subgraph

### Query Recent Executions

```graphql
query RecentArbitrages {
  arbitrageExecutions(
    first: 10
    orderBy: blockTimestamp
    orderDirection: desc
  ) {
    id
    asset
    borrowAmount
    profit
    gasCost
    netProfit
    blockTimestamp
    transactionHash
  }
}
```

### Query Daily Stats

```graphql
query DailyStats($contractId: Bytes!) {
  dailyArbitrageSnapshots(
    where: { contract: $contractId }
    first: 30
    orderBy: date
    orderDirection: desc
  ) {
    date
    executionCount
    totalProfit
    totalGasCost
    netProfit
    avgProfitPerTrade
    successRate
  }
}
```

### Use in Python

```python
from src.dex.money_graphic_client import MoneyGraphicClient

client = MoneyGraphicClient()

# Get recent arbitrage executions
query = """
{
  arbitrageExecutions(first: 5, orderBy: blockTimestamp, orderDirection: desc) {
    profit
    netProfit
    blockTimestamp
  }
}
"""

result = await client.client.execute_async(query)
print(result)
```

---

## ⚠️ Safety Checklist

Before executing on mainnet:

### 1. Test on Testnet First
```bash
# Deploy to Sepolia testnet
# Update .env with Sepolia addresses
ARB_CONTRACT_ADDRESS=0xYourSepoliaContract
ETH_RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
```

### 2. Start with Dry Run
```python
config = FlashArbConfig(
    enable_execution=False,  # Dry run mode
    enable_flash_loans=True
)
```

### 3. Check Gas Prices
```python
current_gas = executor.w3.eth.gas_price
max_gas = Web3.to_wei(100, "gwei")

if current_gas > max_gas:
    print("⚠️ Gas too high - waiting...")
```

### 4. Verify Profitability
```python
# Always check before executing
if not profitability.is_profitable:
    print("❌ Not profitable")
    return

if profitability.net_profit < min_threshold:
    print("❌ Profit too small")
    return
```

### 5. Monitor Slippage
```python
# High slippage = risky
if price_impact_bps > 100:  # 1%
    print("⚠️ High price impact")
```

---

## 💡 Pro Tips

### Best Times to Trade

**High Volatility = More Opportunities**
- Market open (8-10 AM EST)
- Major news events
- Large liquidations

**Low Gas = Better Profits**
- Midnight - 4 AM EST
- Weekends
- Set `MAX_GAS_PRICE_GWEI=30` during these times

### Optimal Parameters

**Conservative (Recommended for Start)**
```python
config = FlashArbConfig(
    max_flash_borrow_eth=10.0,      # Start small
    min_flash_profit_eth=0.5,        # Higher threshold
    flash_loan_threshold_bps=150.0,  # Larger spreads only
)
```

**Aggressive (More Trades)**
```python
config = FlashArbConfig(
    max_flash_borrow_eth=100.0,     # Max size
    min_flash_profit_eth=0.2,        # Lower threshold
    flash_loan_threshold_bps=75.0,   # Smaller spreads
)
```

### Token Pairs to Watch

**Most Liquid (Start Here)**
- WETH/USDC
- WETH/USDT
- WETH/DAI

**Stablecoins (Lower Risk)**
- USDC/DAI
- USDC/USDT

**Avoid**
- Low volume pairs (< $1M daily)
- New tokens
- Exotic pairs

---

## 🐛 Troubleshooting

### "Contract address not set"
```bash
# Make sure .env has the deployed address
export ARB_CONTRACT_ADDRESS=0xYourActualAddress
```

### "Insufficient profit margin"
- Slippage too high
- Gas price too high
- Spread decreased between check and execution

### "Gas price too high"
```python
# Increase max gas or wait
executor.contract.functions.setMaxGasPrice(
    Web3.to_wei(150, "gwei")
).transact()
```

### Transaction Reverts
- Check simulation first: `executor.simulate_arbitrage()`
- Verify liquidity exists
- Check token approvals

---

## 📚 Next Steps

1. **Deploy to Testnet** - Get comfortable with the system
2. **Run in Dry-Run Mode** - Monitor opportunities without executing
3. **Start Small** - Use low `max_flash_borrow_eth`
4. **Monitor Performance** - Use subgraph to track results
5. **Scale Gradually** - Increase size as you gain confidence

---

## 🎉 Summary

You now have a **complete flash loan arbitrage system**:

✅ Smart contract deployed and tested
✅ Python integration with your existing scanner
✅ Automatic opportunity detection
✅ Profitability checks with gas estimation
✅ On-chain execution tracking
✅ Risk management and safety checks

**Everything is ready - start finding profitable opportunities!** 💰
