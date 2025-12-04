# 🌐 MAINNET CONFIGURATION REFERENCE

**⚠️ WARNING: MAINNET USES REAL MONEY! USE WITH CAUTION!**

---

## 📍 Your Deployed Mainnet Contract

**Contract Address:** `0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0`
**Etherscan:** https://etherscan.io/address/0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0
**Deployer Wallet:** `0x31fcD43a349AdA21F3c5Df51D66f399bE518a912`

---

## 🔧 Mainnet Configuration (.env)

```bash
# ============================================================================
# MAINNET FLASH LOAN ARBITRAGE CONFIGURATION
# ============================================================================

# Your deployed arbitrage contract
ARB_CONTRACT_ADDRESS=0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0

# Ethereum Mainnet RPC (use your Alchemy/Infura key)
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/vZuXI4mrngK8K5m-FyIQ0
# Alternative Infura: https://mainnet.infura.io/v3/YOUR_INFURA_KEY

# Your wallet private key (⚠️ KEEP SECRET!)
PRIVATE_KEY=0xfc6a12d09b0bfaf72da0f14bf4a914226b683c810ee3eb07bb041e29dbd1fbcc

# Gas settings
MAX_GAS_PRICE_GWEI=100  # Adjust based on network conditions
GAS_ESTIMATE=350000     # Estimated gas for flash loan transactions

# Profit thresholds
MIN_PROFIT_THRESHOLD_ETH=0.5  # Minimum profit to execute (in ETH)
SLIPPAGE_TOLERANCE_BPS=50     # 0.5% slippage tolerance

# Safety settings (RECOMMENDED FOR MAINNET)
DRY_RUN=true  # Set to false only when ready for real trading!
ENABLE_EXECUTION=false  # Additional safety flag
```

---

## 🏛️ Mainnet Protocol Addresses

Your contract was deployed with these mainnet addresses:

| Protocol | Address | Purpose |
|----------|---------|---------|
| **Aave V3 Pool** | `0x87870Bca3f5FD6335c3f4d4C530Eed06fb5de523` | Flash loan provider |
| **Uniswap V3 Router** | `0xE592427A0AEce92De3Edee1F18E0157C05861564` | DEX swaps |
| **WETH** | `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` | Wrapped Ether |
| **USDC** | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | USDC stablecoin |
| **USDT** | `0xdAC17F958D2ee523a2206206994597C13D831ec7` | Tether stablecoin |
| **DAI** | `0x6B175474E89094C44Da98b954EedeAC495271d0F` | DAI stablecoin |

---

## 🌐 Mainnet RPC Endpoints

### Option 1: Alchemy (Current)
```bash
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/vZuXI4mrngK8K5m-FyIQ0
```

### Option 2: Infura
Get API key: https://infura.io/
```bash
ETHEREUM_RPC_URL=https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID
```

### Option 3: QuickNode
Get endpoint: https://quicknode.com/
```bash
ETHEREUM_RPC_URL=https://your-endpoint.quiknode.pro/YOUR_KEY/
```

---

## 💰 Mainnet Wallet Requirements

### Minimum Balance Requirements:
- **Bare minimum:** 0.05 ETH (~$175)
- **Recommended:** 0.1 ETH (~$350)
- **Comfortable:** 0.5 ETH (~$1,750)
- **Production:** 1-2 ETH (~$3,500-$7,000)

### Cost Breakdown:
| Transaction Type | Est. Gas | Cost @ 50 Gwei | Cost @ 100 Gwei |
|-----------------|----------|----------------|-----------------|
| Flash Loan Arb | 350k gas | 0.0175 ETH ($61) | 0.035 ETH ($122) |
| Failed Transaction | 100k gas | 0.005 ETH ($17) | 0.01 ETH ($35) |

---

## ⚙️ Gas Price Settings

### Conservative (Safer):
```bash
MAX_GAS_PRICE_GWEI=50
```

### Moderate (Balanced):
```bash
MAX_GAS_PRICE_GWEI=100
```

### Aggressive (Faster, More Expensive):
```bash
MAX_GAS_PRICE_GWEI=200
```

**Check current gas prices:** https://etherscan.io/gastracker

---

## 🛡️ Safety Configuration for Mainnet

### Phase 1: Testing with Small Amounts
```bash
MIN_PROFIT_THRESHOLD_ETH=0.5
MAX_FLASH_BORROW_ETH=1.0
SLIPPAGE_TOLERANCE_BPS=50  # 0.5%
DRY_RUN=false
ENABLE_EXECUTION=true
```

### Phase 2: Production with Larger Amounts
```bash
MIN_PROFIT_THRESHOLD_ETH=0.3
MAX_FLASH_BORROW_ETH=10.0
SLIPPAGE_TOLERANCE_BPS=30  # 0.3%
DRY_RUN=false
ENABLE_EXECUTION=true
```

---

## 📊 Monitoring & Alerts

### Track Your Transactions:
- **Your Contract:** https://etherscan.io/address/0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0
- **Your Wallet:** https://etherscan.io/address/0x31fcD43a349AdA21F3c5Df51D66f399bE518a912

### Gas Tracker:
- https://etherscan.io/gastracker
- https://www.gasnow.org/

### MEV Protection:
Consider using:
- Flashbots RPC: `https://rpc.flashbots.net`
- Eden Network: `https://api.edennetwork.io/v1/rpc`

---

## ⚠️ MAINNET CHECKLIST (Before Going Live)

- [ ] Wallet has minimum 0.1 ETH
- [ ] Contract verified on Etherscan
- [ ] Tested extensively on Sepolia testnet
- [ ] Gas price limits configured
- [ ] Profit thresholds set appropriately
- [ ] Monitoring/alerts set up
- [ ] Emergency stop procedure documented
- [ ] Private key backed up securely (offline!)
- [ ] Started with DRY_RUN=true first
- [ ] Tested with small amounts before scaling up

---

## 🚨 Emergency Procedures

### If Something Goes Wrong:

1. **Stop the bot immediately** (Ctrl+C)
2. **Set DRY_RUN=true in .env**
3. **Check Etherscan for pending/failed transactions**
4. **Withdraw funds from contract if needed**
5. **Review logs for errors**

### Withdraw Funds from Contract:
The contract owner can call `rescueTokens()` to withdraw any stuck tokens.

---

## 📝 Notes

- **Created:** 2025-11-28
- **Network:** Ethereum Mainnet (Chain ID: 1)
- **Contract Deployment Tx:** https://etherscan.io/tx/0xef794fe2fb873158f789004b43488390135f80abd0b1f0cc60f7210e64b1c458
- **Total Deployment Cost:** 0.00013051 ETH

---

## 🎓 Best Practices

1. **Always test on Sepolia first**
2. **Start with DRY_RUN=true on mainnet**
3. **Use small amounts initially**
4. **Monitor gas prices constantly**
5. **Set up alerts for failed transactions**
6. **Keep sufficient ETH for gas**
7. **Review every transaction on Etherscan**
8. **Never share your private key**
9. **Keep backups of your configuration**
10. **Document any changes you make**

---

**Remember: With great power comes great responsibility!** 🕷️💰
