Analyze gas price trends:

1. Fetch last 100 blocks of gas price data (Ethereum mainnet)
2. Calculate statistics:
   - Current base fee (EIP-1559)
   - Average gas price (24h)
   - 95th percentile
   - Lowest prices seen (off-peak hours)
3. Compare to configured GAS_PRICE_CAP_ETH
4. Display optimal execution windows (when gas < 30 gwei)
5. Estimate cost savings from patient execution

Use src/live/gas_oracle.py or direct RPC eth_feeHistory calls.
