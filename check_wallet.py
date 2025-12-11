"""Quick script to check wallet balance and contract connection."""

from decimal import Decimal

from web3 import Web3
from src.dex.flash_loan_executor import FlashLoanExecutor

def main():
    print("=" * 60)
    print("WALLET & CONTRACT STATUS CHECK")
    print("=" * 60)

    try:
        # Initialize executor
        executor = FlashLoanExecutor()

        # Check connection
        print(f"\n✅ Connected to Ethereum: {executor.w3.is_connected()}")
        print(f"📍 Network: {executor.w3.eth.chain_id}")

        # Check wallet
        wallet_address = executor.account.address
        balance_wei = executor.w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(str(Web3.from_wei(balance_wei, "ether")))

        print(f"\n💼 Wallet Address: {wallet_address}")
        print(f"💰 Balance: {balance_eth:.4f} ETH (${balance_eth * Decimal('3500'):.2f} @ $3500/ETH)")

        # Check contract
        contract_address = executor.settings.arb_contract_address
        print(f"\n📄 Contract Address: {contract_address}")
        if contract_address:
            contract_checksum = Web3.to_checksum_address(contract_address)
            contract_code = executor.w3.eth.get_code(contract_checksum)
            print(f"✅ Contract Deployed: {len(contract_code) > 0}")
        else:
            print("⚠️  No contract address configured")

        # Gas price check
        gas_price_wei = executor.w3.eth.gas_price
        gas_price_gwei = Decimal(str(Web3.from_wei(gas_price_wei, "gwei")))
        max_gas_gwei = Decimal(str(executor.settings.max_gas_price_gwei))

        gas_price_ok = gas_price_gwei <= max_gas_gwei
        print(f"\n⛽ Current Gas Price: {gas_price_gwei:.2f} Gwei")
        print(f"⛽ Max Gas Price: {max_gas_gwei} Gwei")
        print(f"{'✅' if gas_price_ok else '⚠️'} Gas price {'acceptable' if gas_price_ok else 'too high'}")

        # Estimate costs
        estimated_gas = Decimal("350000")
        cost_eth = (estimated_gas * gas_price_gwei) / Decimal(1_000_000_000)
        cost_usd = cost_eth * Decimal("3500")
        print("\n💵 ESTIMATED COSTS:")
        print(f"   Flash loan tx: ~350k gas = ~{cost_eth:.4f} ETH (${cost_usd:.2f})")
        print("   Min recommended balance: 0.1 ETH")

        if balance_eth < Decimal("0.01"):
            print("\n⚠️  WARNING: Balance very low! Add ETH for gas fees.")
        elif balance_eth < Decimal("0.1"):
            print("\n⚠️  CAUTION: Consider adding more ETH for safety.")
        else:
            print("\n✅ Balance sufficient for multiple transactions!")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
