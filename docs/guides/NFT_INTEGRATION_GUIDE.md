# OpenSea NFT Integration Guide

## Overview

Your arbitrage dashboard now displays your NFT collection from OpenSea.io using the 2025 OpenSea API v2 standards.

## What's Been Added

### 1. OpenSea Client Module
- **File**: `src/nft/opensea_client.py`
- Modern Python client with async/await patterns
- Type-safe with dataclasses
- Supports all OpenSea chains (Ethereum, Polygon, Base, Arbitrum, etc.)

### 2. API Endpoints

#### Get NFTs by Wallet
```
GET /api/nft/wallet/{wallet_address}?chain=ethereum
```

**Example**:
```bash
curl http://localhost:8080/api/nft/wallet/0x31fcd43a349ada21f3c5df51d66f399be518a912?chain=ethereum
```

**Response**:
```json
{
  "success": true,
  "wallet": "0x31fcd43a349ada21f3c5df51d66f399be518a912",
  "chain": "ethereum",
  "count": 5,
  "nfts": [
    {
      "identifier": "1234",
      "collection": "cool-cats-nft",
      "name": "Cool Cat #1234",
      "image_url": "https://...",
      "opensea_url": "https://opensea.io/assets/ethereum/0x.../1234",
      "contract": "0x...",
      "token_standard": "erc721"
    }
  ]
}
```

#### Get Collection Info
```
GET /api/nft/collection/{collection_slug}
```

**Example**:
```bash
curl http://localhost:8080/api/nft/collection/boredapeyachtclub
```

### 3. Dashboard Integration

Your NFT collection now appears on the dashboard at:
- **URL**: http://localhost:8080/classic

**Features**:
- Grid layout showing all your NFTs
- Hover effects for visual feedback
- Click any NFT to open it on OpenSea
- Real-time loading status
- Error handling with helpful messages

## Configuration

### Environment Variables (.env)

```bash
# OpenSea API v2 credentials
OPENSEA_API_KEY=8ba24065ef8f4fd08f02f821f62135ee

# OpenSea MCP Token (for AI features)
OPENSEA_MCP_TOKEN=042qSNLGgnYsB0dDwjt1ngpXwcGvI7Dim3h4B3HjmER95Lpa

# Wallets to track
NFT_WALLET_ADDRESSES=0x31fcd43a349ada21f3c5df51d66f399be518a912,0x21E722833CE4C3e8CE68F14D159456744402b48C

# Chains to fetch from
NFT_CHAINS=ethereum,polygon
```

## API Key Details

Your OpenSea API credentials:
- **API Key Name**: opensea_money
- **API Key**: 8ba24065ef8f4fd08f02f821f62135ee
- **Expiration**: Dec 7, 2030
- **MCP Token**: 042qSNLGgnYsB0dDwjt1ngpXwcGvI7Dim3h4B3HjmER95Lpa

## Usage

### Start the Dashboard

```bash
./start_dashboard.sh
```

Then navigate to: http://localhost:8080/classic

### Test the API Directly

```python
import asyncio
from src.nft.opensea_client import get_wallet_nfts

async def test():
    nfts = await get_wallet_nfts(
        "0x31fcd43a349ada21f3c5df51d66f399be518a912",
        chain="ethereum"
    )
    print(f"Found {len(nfts)} NFTs")
    for nft in nfts:
        print(f"  - {nft.name} ({nft.collection})")

asyncio.run(test())
```

## OpenSea API v2 Features (2025)

### Supported Endpoints

1. **List NFTs by Account** - Get all NFTs owned by a wallet
2. **Get Collection** - Fetch collection metadata and stats
3. **List NFTs by Collection** - Browse collection items
4. **Get NFT** - Individual NFT details

### Supported Chains

- Ethereum (mainnet)
- Polygon
- Base
- Arbitrum
- Optimism
- BNB Chain
- Avalanche
- zkSync
- More chains added regularly

## OpenSea MCP (Model Context Protocol)

Your dashboard is ready for AI integration using OpenSea's MCP server.

**MCP Configuration**:
```json
{
  "mcpServers": {
    "OpenSea": {
      "url": "https://mcp.opensea.io/mcp",
      "headers": {
        "Authorization": "Bearer 042qSNLGgnYsB0dDwjt1ngpXwcGvI7Dim3h4B3HjmER95Lpa"
      }
    }
  }
}
```

**AI-Powered Features**:
- Natural language NFT search
- Portfolio analysis
- Market trend detection
- Automated trading signals
- Collection recommendations

## Rate Limits

**With API Key** (your tier):
- 4 requests/second
- Suitable for personal dashboards

**Without API Key** (fallback):
- 2 requests/second
- Limited to public endpoints

## Troubleshooting

### NFTs Not Showing

1. **Check API Key**: Verify `OPENSEA_API_KEY` is set in `.env`
2. **Check Wallet Address**: Ensure address owns NFTs on the selected chain
3. **Check Network**: Verify RPC endpoints are working
4. **Check Logs**: Look for errors in console or `structlog` output

### Common Errors

**"No NFTs found"**
- Wallet may not own any NFTs on this chain
- Try different chains (ethereum, polygon, etc.)
- Verify wallet address is correct

**"API Error 401"**
- API key is invalid or expired
- Check your OpenSea developer dashboard

**"API Error 429"**
- Rate limit exceeded
- Wait 60 seconds and try again
- Consider upgrading API tier

## Code Architecture

### Type Safety

All code uses modern Python type hints:
```python
async def get_nfts_by_account(
    wallet_address: str,
    chain: str = "ethereum",
    limit: int = 50,
) -> list[NFTMetadata]:
```

### Error Handling

Graceful degradation with structured logging:
```python
try:
    nfts = await client.get_nfts_by_account(wallet, chain)
except HTTPStatusError as e:
    log.error("opensea.api_error", status=e.response.status_code)
    return []
```

### Async Patterns

Non-blocking I/O for dashboard performance:
```python
async with AsyncClient(timeout=30.0) as client:
    response = await client.get(endpoint, headers=headers)
```

## Next Steps

### Potential Enhancements

1. **NFT Floor Price Tracking**: Monitor collection floor prices
2. **Portfolio Valuation**: Calculate total NFT portfolio value
3. **Rarity Scoring**: Show trait rarity and ranking
4. **Sale Alerts**: Get notified of sales in your collections
5. **Cross-Chain Aggregation**: Combine NFTs from multiple chains
6. **Historical Data**: Track NFT value over time

### Advanced Features

- Integrate with NFT lending protocols (Blur, Bend)
- Add NFT-collateralized loan tracking
- Connect to NFT liquidity pools
- Build NFT arbitrage scanner (OpenSea vs Blur)

## Resources

- [OpenSea API Documentation](https://docs.opensea.io/reference/api-overview)
- [OpenSea MCP Guide](https://docs.opensea.io/mcp)
- [NFT Endpoints Reference](https://docs.opensea.io/reference/list_nfts_by_collection)
- [API Changelog](https://docs.opensea.io/changelog)

## Support

For issues or questions:
- Check OpenSea docs: https://docs.opensea.io/
- Email OpenSea support: [email protected]
- Join OpenSea Discord: discord.gg/opensea

---

**Note**: This integration uses 2025 standards with no deprecated code. All endpoints are OpenSea API v2 with modern async Python patterns.
