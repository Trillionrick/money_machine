# NFT Integration - Quick Reference Card

## 🚀 Quick Start

```bash
# Start dashboard
./start_dashboard.sh

# Open browser
http://localhost:8080/classic

# Test API
curl http://localhost:8080/api/nft/wallet/0x31fcd43a349ada21f3c5df51d66f399be518a912
```

## 📡 API Endpoints

### Get Wallet NFTs
```bash
GET /api/nft/wallet/{address}?chain=ethereum

# Example
curl "http://localhost:8080/api/nft/wallet/0x31fcd43a349ada21f3c5df51d66f399be518a912?chain=ethereum"
```

### Get Collection Info
```bash
GET /api/nft/collection/{slug}

# Example
curl http://localhost:8080/api/nft/collection/boredapeyachtclub
```

## 🔑 Environment Variables

```bash
# .env file
OPENSEA_API_KEY=8ba24065ef8f4fd08f02f821f62135ee
OPENSEA_MCP_TOKEN=042qSNLGgnYsB0dDwjt1ngpXwcGvI7Dim3h4B3HjmER95Lpa
NFT_WALLET_ADDRESSES=0x31fcd43a349ada21f3c5df51d66f399be518a912
NFT_CHAINS=ethereum,polygon
```

## 🐍 Python Usage

```python
import asyncio
from src.nft.opensea_client import get_wallet_nfts

# Fetch NFTs
async def main():
    nfts = await get_wallet_nfts(
        "0x31fcd43a349ada21f3c5df51d66f399be518a912",
        chain="ethereum"
    )
    print(f"Found {len(nfts)} NFTs")

asyncio.run(main())
```

## 🔧 Common Tasks

### Test Integration
```bash
python test_nft_integration.py
```

### Check Logs
```bash
# View structured logs
tail -f logs/arbitrage.log | grep opensea
```

### Update API Key
```bash
# Edit .env
nano .env

# Restart server
pkill -f web_server.py
./start_dashboard.sh
```

## 🌐 Supported Chains

| Chain | Identifier | Status |
|-------|-----------|--------|
| Ethereum | `ethereum` | ✅ Active |
| Polygon | `polygon` | ✅ Active |
| Base | `base` | 🟡 Available |
| Arbitrum | `arbitrum` | 🟡 Available |
| Optimism | `optimism` | 🟡 Available |

## 📊 Response Format

```json
{
  "success": true,
  "wallet": "0x31fcd43a349ada21f3c5df51d66f399be518a912",
  "chain": "ethereum",
  "count": 19,
  "nfts": [
    {
      "identifier": "1234",
      "collection": "cool-nft-collection",
      "name": "Cool NFT #1234",
      "image_url": "https://...",
      "opensea_url": "https://opensea.io/assets/...",
      "contract": "0x...",
      "token_standard": "erc721"
    }
  ]
}
```

## ⚠️ Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 200 | Success | - |
| 400 | Invalid address | Check wallet format |
| 401 | Invalid API key | Update `.env` |
| 429 | Rate limited | Wait 60s |
| 500 | OpenSea error | Check status page |

## 🔍 Troubleshooting

### "No NFTs found"
```bash
# Check different chain
curl "http://localhost:8080/api/nft/wallet/0x...?chain=polygon"

# Verify wallet has NFTs on OpenSea
open "https://opensea.io/0x31fcd43a349ada21f3c5df51d66f399be518a912"
```

### "API key invalid"
```bash
# Verify key in .env
cat .env | grep OPENSEA_API_KEY

# Test key directly
curl -H "x-api-key: YOUR_KEY" https://api.opensea.io/api/v2/collections/boredapeyachtclub
```

### Dashboard not loading NFTs
```bash
# Check browser console (F12)
# Look for errors in Network tab

# Check server logs
tail -f logs/arbitrage.log | grep nft

# Restart server
./start_dashboard.sh
```

## 📈 Performance Tips

1. **Cache responses** (5 min TTL recommended)
2. **Batch requests** for multiple wallets
3. **Use CDN images** (already optimized)
4. **Limit initial load** (50 NFTs max)

## 🔗 Useful Links

- **OpenSea API Docs**: https://docs.opensea.io/
- **Your NFT Collection**: https://opensea.io/0x31fcd43a349ada21f3c5df51d66f399be518a912
- **API Status**: https://status.opensea.io/
- **Dashboard**: http://localhost:8080/classic

## 🛠️ File Locations

```
money_machine/
├── src/nft/
│   ├── __init__.py
│   └── opensea_client.py          # Main client
├── web_server.py                   # API endpoints (line 796+)
├── web_dashboard.html              # Frontend (line 1007+)
├── test_nft_integration.py         # Test script
├── .env                            # Config (line 183+)
├── NFT_INTEGRATION_GUIDE.md        # User guide
├── NFT_TECHNICAL_REFERENCE.md      # Tech docs
└── NFT_QUICK_REFERENCE.md          # This file
```

## 🎯 Rate Limits

| Tier | Rate | Daily Limit |
|------|------|-------------|
| No Key | 2/sec | 17,280 |
| API Key | 4/sec | 345,600 |
| Premium | 10/sec | 864,000 |

**Your Tier**: API Key (4 req/sec)
**Key Expiration**: Dec 7, 2030

## 📞 Support Contacts

- **OpenSea Support**: [email protected]
- **OpenSea Discord**: discord.gg/opensea
- **API Docs**: https://docs.opensea.io/

---

**Last Updated**: 2025-12-08
**Quick Reference Version**: 1.0
