"""Quick script to check wallet balance and contract connection."""

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
        balance_eth = Web3.from_wei(balance_wei, 'ether')

        print(f"\n💼 Wallet Address: {wallet_address}")
        print(f"💰 Balance: {balance_eth:.4f} ETH (${balance_eth * 3500:.2f} @ $3500/ETH)")

        # Check contract
        print(f"\n📄 Contract Address: {executor.settings.arb_contract_address}")
        contract_code = executor.w3.eth.get_code(executor.settings.arb_contract_address)
        print(f"✅ Contract Deployed: {len(contract_code) > 0}")

        # Gas price check
        gas_price_wei = executor.w3.eth.gas_price
        gas_price_gwei = Web3.from_wei(gas_price_wei, 'gwei')
        max_gas_gwei = executor.settings.max_gas_price_gwei

        print(f"\n⛽ Current Gas Price: {gas_price_gwei:.2f} Gwei")
        print(f"⛽ Max Gas Price: {max_gas_gwei} Gwei")
        print(f"{'✅' if gas_price_gwei <= max_gas_gwei else '⚠️'} Gas price {'acceptable' if gas_price_gwei <= max_gas_gwei else 'too high'}")

        # Estimate costs
        print(f"\n💵 ESTIMATED COSTS:")
        print(f"   Flash loan tx: ~350k gas = ~{0.35 * gas_price_gwei:.4f} ETH (${0.35 * gas_price_gwei * 3500:.2f})")
        print(f"   Min recommended balance: 0.1 ETH")

        if balance_eth < 0.01:
            print("\n⚠️  WARNING: Balance very low! Add ETH for gas fees.")
        elif balance_eth < 0.1:
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
