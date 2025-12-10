# AQUA BSC Arbitrage - Remix Deployment Guide

Complete guide for deploying and operating the AQUA token arbitrage system on BSC using Remix IDE.

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Smart Contract Deployment (Remix)](#smart-contract-deployment-remix)
4. [Contract Configuration](#contract-configuration)
5. [Python Backend Setup](#python-backend-setup)
6. [Testing Strategy](#testing-strategy)
7. [Production Execution](#production-execution)

---

## Overview

### System Architecture

**Arbitrage Strategy:**
```
1. Borrow WBNB from PancakeSwap V3 (flash loan, 0% upfront fee)
2. Buy AQUA on DEX with lower price (PancakeSwap or Biswap)
3. Sell AQUA on DEX with higher price
4. Repay flash loan + fee
5. Keep profit in WBNB
```

**Key Components:**
- **Smart Contract:** `AQUABSCArbitrage.sol` (BSC mainnet)
- **Python Backend:** `aqua_arb_runner.py` (monitors & executes)
- **AQUA Token:** `0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991` (BEP-20)

---

## Prerequisites

### Required Accounts & Tools

1. **MetaMask Wallet**
   - Connected to BSC Mainnet (Chain ID: 56)
   - RPC: `https://bsc-dataseed1.binance.org:443`
   - Funded with minimum 0.5 BNB for:
     - Contract deployment (~0.01 BNB)
     - Gas for transactions (~0.002 BNB per arb)
     - Flash loan collateral (temporary)

2. **Remix IDE**
   - URL: https://remix.ethereum.org
   - Compiler version: 0.8.25
   - Injected Provider (MetaMask)

3. **BSC Testnet (Recommended for Testing)**
   - Chain ID: 97
   - RPC: `https://data-seed-prebsc-1-s1.binance.org:8545`
   - Faucet: https://testnet.binance.org/faucet-smart

### Required Token Addresses (BSC Mainnet)

```solidity
AQUA:  0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991
WBNB:  0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c
BUSD:  0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56
USDT:  0x55d398326f99059fF775485246999027B3197955
```

---

## Smart Contract Deployment (Remix)

### Step 1: Open Remix

1. Navigate to https://remix.ethereum.org
2. Create new file: `AQUABSCArbitrage.sol`
3. Copy contract code from `/contracts/AQUABSCArbitrage.sol`

### Step 2: Compile Contract

1. **Click "Solidity Compiler" tab (left sidebar)**
2. **Configure compiler:**
   - Compiler version: `0.8.25`
   - Enable optimization: ✅ (200 runs recommended)
   - EVM Version: `paris` (or default)
3. **Click "Compile AQUABSCArbitrage.sol"**
4. **Verify:**
   - Green checkmark appears
   - No errors in console
   - Warning about `SPDX license identifier` is normal

### Step 3: Deploy to BSC

1. **Click "Deploy & Run Transactions" tab**
2. **Configure deployment:**
   - Environment: **Injected Provider - MetaMask**
   - Account: (your wallet address will auto-populate)
   - Gas Limit: `3000000` (auto-estimated)
   - Value: `0` (no BNB needed in constructor)
3. **Verify MetaMask:**
   - Network shows "BNB Smart Chain Mainnet"
   - If not, add BSC: [BSC Network Setup](https://academy.binance.com/en/articles/connecting-metamask-to-binance-smart-chain)
4. **Select Contract:**
   - Contract dropdown: `AQUABSCArbitrage`
5. **Deploy:**
   - Click orange "Deploy" button
   - MetaMask will prompt for approval
   - Confirm transaction (gas: ~0.01 BNB)
6. **Wait for confirmation:**
   - Check BSCScan: https://bscscan.com
   - Copy contract address from "Deployed Contracts" section in Remix

**Important:** Save your deployed contract address! You'll need it for configuration.

Example deployed address format: `0x1234...abcd`

---

## Contract Configuration

After deployment, configure the contract with pool addresses and parameters.

### Step 1: Find Pool Addresses

**PancakeSwap V3 AQUA/WBNB Pool:**
```bash
# Method 1: PancakeSwap Info Page
Visit: https://pancakeswap.finance/info/v3/bsc/pools
Search: "AQUA/WBNB"
Copy pool address

# Method 2: Query Factory (Advanced)
Factory: 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865
Call getPool(AQUA, WBNB, 2500) // 0.25% fee tier
```

**Biswap AQUA/WBNB Pool:**
```bash
# Visit Biswap Analytics
Visit: https://biswap.org/info/pool
Search: "AQUA/WBNB"
Copy pool address
```

If pools don't exist, you'll need to create liquidity first (outside scope of this guide).

### Step 2: Configure Pools in Remix

1. **In Remix "Deployed Contracts" section:**
2. **Expand your contract**
3. **Find `configurePools` function**
4. **Fill parameters:**
   ```
   _aquaWbnbPoolPancake: 0x... (PancakeSwap V3 pool address)
   _aquaWbnbPoolBiswap:  0x... (Biswap pool address)
   ```
5. **Click "transact" (orange button)**
6. **Confirm in MetaMask**
7. **Wait for confirmation**

### Step 3: Set Minimum Profit (Optional)

Default is 50 BPS (0.5%), adjust if needed:

```solidity
// In Remix
setMinProfitBPS(100) // For 1.0% minimum profit
```

### Step 4: Verify Configuration

**Call view functions to verify:**
```solidity
aquaWbnbPoolPancake() // Should return pool address
minProfitBPS()        // Should return 50 (or your custom value)
```

---

## Python Backend Setup

### Step 1: Environment Configuration

Create or update `.env` file in project root:

```bash
# BSC Configuration
BSC_RPC_URL=https://bsc-dataseed1.binance.org:443
BSC_RPC_BACKUP=https://bsc-dataseed2.binance.org:443
BSC_PRIVATE_KEY=your_private_key_here  # Without 0x prefix

# Deployed Contract
BSC_AQUA_CONTRACT=0x...  # Your deployed contract address

# Token Addresses (BSC Mainnet)
AQUA_ADDRESS=0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991
WBNB_ADDRESS=0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c

# PancakeSwap V3
PANCAKE_V3_ROUTER=0x13f4EA83D0bd40E75C8222255bc855a974568Dd4
PANCAKE_V3_FACTORY=0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865
PANCAKE_V3_POOL_AQUA_WBNB=0x...  # From Step 1 above

# Biswap
BISWAP_ROUTER=0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8

# Gas Settings
BSC_MAX_GAS_PRICE_GWEI=5
BSC_GAS_ESTIMATE=250000

# Risk Management
MIN_PROFIT_THRESHOLD_BNB=0.05  # Minimum 0.05 BNB profit
SLIPPAGE_TOLERANCE_BPS=100     # 1% slippage tolerance
```

**Security Warning:** Never commit `.env` to version control!

### Step 2: Install Dependencies

```bash
# From project root
pip install -r requirements.txt

# If you get import errors, install specific packages:
pip install web3 eth-typing pydantic pydantic-settings structlog
```

### Step 3: Test Connection

```bash
# Test BSC connection
python -c "
from src.dex.bsc_connector import BSCConnector
connector = BSCConnector()
print(f'Connected to BSC, Chain ID: {connector.get_chain_id()}')
print(f'Block number: {connector.w3.eth.block_number}')
"
```

Expected output:
```
Connected to BSC, Chain ID: 56
Block number: 35000000  # (approximate)
```

---

## Testing Strategy

### Phase 1: Local Simulation (No Real Execution)

**Test 1: BSC Connector**
```python
# File: test_bsc_connector.py
import asyncio
from src.dex.bsc_connector import BSCConnector

async def test_connector():
    connector = BSCConnector()

    # Test AQUA price fetch
    price = await connector.get_aqua_price("WBNB")
    print(f"AQUA/WBNB price: {price}")

    # Test balance
    aqua_balance = await connector.get_token_balance(
        "0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991"
    )
    print(f"AQUA balance: {aqua_balance}")

asyncio.run(test_connector())
```

**Test 2: Flash Loan Executor (Dry Run)**
```python
# File: test_flash_executor.py
from src.dex.bsc_flash_executor import BSCFlashLoanExecutor

executor = BSCFlashLoanExecutor()

# Test with dry run (no real tx)
receipt = executor.execute_arbitrage(
    borrow_amount_bnb=1.0,
    buy_on_pancake=True,
    dry_run=True  # IMPORTANT: Dry run only
)

print(f"Dry run result: {receipt}")

# Check contract stats
stats = executor.get_contract_stats()
print(f"Contract stats: {stats}")
```

**Test 3: Opportunity Scanner**
```python
# File: test_scanner.py
import asyncio
from src.live.aqua_arb_runner import AQUAArbitrageRunner

async def test_scanner():
    runner = AQUAArbitrageRunner(
        scan_interval=10.0,
        min_profit_bps=50.0,
        enable_execution=False  # Dry run
    )

    # Scan once
    opportunity = await runner.scan_for_opportunities()
    print(f"Opportunity found: {opportunity}")

asyncio.run(test_scanner())
```

### Phase 2: BSC Testnet Testing

1. **Switch to BSC Testnet**
   - Update `.env`: `BSC_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545`
   - Redeploy contract on testnet
   - Get testnet BNB from faucet

2. **Execute Small Test Trade**
   ```python
   # Enable execution with small amount
   executor.execute_arbitrage(
       borrow_amount_bnb=0.01,  # Tiny amount
       buy_on_pancake=True,
       dry_run=False
   )
   ```

3. **Verify on Testnet BSCScan:**
   - https://testnet.bscscan.com
   - Check transaction logs
   - Verify profit/loss

### Phase 3: Mainnet Small Amount

Once testnet works perfectly:

1. **Deploy to mainnet** (follow deployment steps above)
2. **Start with minimum:** `0.1 BNB` borrow amount
3. **Monitor closely:** Check every transaction on BSCScan
4. **Gradual increase:** Only increase after 10+ successful arbitrages

---

## Production Execution

### Running the Scanner

**Method 1: Direct Python Script**
```bash
# Dry run mode (safe, no real execution)
python src/live/aqua_arb_runner.py

# Production mode (REAL MONEY - BE CAREFUL)
# Edit aqua_arb_runner.py, set:
# enable_execution=True
python src/live/aqua_arb_runner.py
```

**Method 2: Integrated with Existing System**
```python
# In your main arbitrage script
from src.live.aqua_arb_runner import AQUAArbitrageRunner

async def run_aqua_arbitrage():
    runner = AQUAArbitrageRunner(
        scan_interval=5.0,
        min_profit_bps=50.0,
        max_borrow_bnb=10.0,
        enable_execution=True,  # Set False for dry run
    )

    await runner.run()
```

### Monitoring & Alerts

**Check Logs:**
```bash
# Real-time log monitoring
tail -f logs/arbitrage.log | grep "aqua_arb"

# Pretty print JSON logs
tail -f logs/arbitrage.log | jq 'select(.logger | contains("aqua_arb"))'
```

**Monitor Contract:**
```python
# Check contract statistics
from src.dex.bsc_flash_executor import BSCFlashLoanExecutor

executor = BSCFlashLoanExecutor()
stats = executor.get_contract_stats()

print(f"""
Total Arbitrages: {stats['total_arbitrages']}
Total Profit: {stats['total_profit']} wei
Failed Attempts: {stats['failed_attempts']}
""")
```

### Safety Parameters

**Circuit Breakers (Auto-configured):**
- Max daily loss: -0.5 ETH (equivalent)
- Max consecutive failures: 5
- High gas price cutoff: 5 gwei (BSC)

**Manual Overrides:**
```python
# In Remix, call emergency functions:
setMaxGasPrice(3000000000)  // 3 gwei max
setSlippageTolerance(50)    // 0.5% slippage
rescueFunds(WBNB_ADDRESS)   // Emergency withdrawal
```

---

## Troubleshooting

### Common Issues

**1. "Gas price too high" error**
```
Solution: BSC gas spikes happen. Increase max gas price:
contract.setMaxGasPrice(10 gwei)  // In Remix
```

**2. "Not profitable" after flash loan**
```
Causes:
- Price moved during execution (MEV)
- Slippage exceeded estimates
- Gas costs higher than expected

Solutions:
- Increase min profit threshold: setMinProfitBPS(100)
- Reduce borrow amount for lower slippage
- Monitor mempool for competition
```

**3. Flash loan callback fails**
```
Check:
1. Pool addresses configured correctly
2. Sufficient liquidity in pools (> 10 BNB)
3. AQUA trading not paused on DEXs
4. Contract has token approvals (auto-handled)
```

**4. Python script can't connect to BSC**
```bash
# Test RPC manually
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  https://bsc-dataseed1.binance.org:443

# Try backup RPC
export BSC_RPC_URL=https://bsc-dataseed2.binance.org:443
```

### Emergency Procedures

**Stop All Trading:**
```python
# In Python
from src.ai.circuit_breakers import get_circuit_breaker_manager

breakers = get_circuit_breaker_manager()
breakers.disable_trading("manual_intervention")
```

**Withdraw Funds:**
```solidity
// In Remix
rescueFunds(WBNB_ADDRESS)  // Send to owner
rescueBNB()                // Rescue any BNB
```

**Transfer Ownership:**
```solidity
// In Remix (from current owner account)
transferOwnership(0x...)  // New owner address
```

---

## Performance Optimization

### Gas Optimization

**Current gas usage:** ~250k gas per arbitrage

**Optimization tips:**
1. Use `view` functions before execution to validate
2. Batch multiple arbitrages if possible
3. Monitor gas price, execute during low-traffic hours

### Spread Detection

**Improve opportunity detection:**
1. Add more DEX integrations (MDEX, ApeSwap)
2. Implement websocket price feeds (faster than polling)
3. Use on-chain price oracles for validation

### Profitability Threshold

**Recommended minimums by borrow amount:**
```
1 BNB borrow:  50 BPS (0.5%) = 0.005 BNB profit
5 BNB borrow:  40 BPS (0.4%) = 0.020 BNB profit
10 BNB borrow: 30 BPS (0.3%) = 0.030 BNB profit
```

Adjust based on your risk tolerance and gas costs.

---

## Resources

### BSC Network
- **Mainnet RPC:** https://bsc-dataseed1.binance.org:443
- **Testnet RPC:** https://data-seed-prebsc-1-s1.binance.org:8545
- **BSCScan:** https://bscscan.com
- **Testnet Faucet:** https://testnet.binance.org/faucet-smart

### DEX Platforms
- **PancakeSwap V3:** https://pancakeswap.finance/info/v3/bsc
- **Biswap:** https://biswap.org
- **PancakeSwap Docs:** https://docs.pancakeswap.finance/

### AQUA Token
- **Contract:** 0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991
- **Planet Finance:** https://planetfinance.io
- **CoinGecko:** https://www.coingecko.com/en/coins/planet-finance

### Development Tools
- **Remix IDE:** https://remix.ethereum.org
- **MetaMask:** https://metamask.io
- **Web3.py Docs:** https://web3py.readthedocs.io/

---

## Contact & Support

For issues specific to this codebase:
- Check existing documentation in `/documentation/`
- Review logs in `/logs/arbitrage.log`
- Test in dry-run mode first

**Security Notice:** This system handles real funds. Always test thoroughly on testnet before mainnet deployment.

---

## Appendix: Complete Deployment Checklist

- [ ] MetaMask configured for BSC mainnet
- [ ] Minimum 0.5 BNB in wallet
- [ ] Contract compiled in Remix (0.8.25)
- [ ] Contract deployed to BSC
- [ ] Contract address saved to `.env`
- [ ] Pool addresses found and configured
- [ ] Minimum profit BPS configured
- [ ] Python dependencies installed
- [ ] BSC connector tested
- [ ] Flash executor tested (dry run)
- [ ] Scanner tested (dry run)
- [ ] Testnet deployment completed
- [ ] Small amount tested on mainnet
- [ ] Production monitoring setup
- [ ] Emergency procedures documented

**Once all checkboxes complete:** You're ready for production! Start with `enable_execution=False` and small amounts.
