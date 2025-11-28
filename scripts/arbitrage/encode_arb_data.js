#!/usr/bin/env node
/**
 * Enhanced Arbitrage Data Encoding Script
 * Compatible with: contracts/EnhancedHighSpeedArbRunner.sol
 *
 * This script encodes arbitrage parameters for flash loan execution
 */

const ethers = require("ethers");

async function main() {
    console.log("=".repeat(80));
    console.log("MONEY MACHINE - ARBITRAGE DATA ENCODER");
    console.log("=".repeat(80));

    // --- CONFIGURATION CONSTANTS ---
    const WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    const USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
    const CONTRACT_ADDRESS = process.env.ARB_CONTRACT_ADDRESS || "0xYOUR_DEPLOYED_CONTRACT_ADDRESS";
    const UNI_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

    // --- VALIDATE CONTRACT ADDRESS ---
    if (CONTRACT_ADDRESS === "0xYOUR_DEPLOYED_CONTRACT_ADDRESS") {
        console.log("\n❌ ERROR: Contract address not set!");
        console.log("=".repeat(80));
        console.log("\nSet the ARB_CONTRACT_ADDRESS environment variable:");
        console.log("  export ARB_CONTRACT_ADDRESS=0xYourDeployedAddress");
        console.log("\nOr update this script directly.\n");
        process.exit(1);
    }

    if (!ethers.utils.isAddress(CONTRACT_ADDRESS)) {
        console.log("\n❌ ERROR: Invalid Ethereum address!");
        console.log(`Provided: ${CONTRACT_ADDRESS}\n`);
        process.exit(1);
    }

    console.log("\n✅ Contract address:", CONTRACT_ADDRESS);

    // Pool fee tiers (Uniswap V3)
    const FEE_LOW = 500;      // 0.05%
    const FEE_MEDIUM = 3000;  // 0.3%
    const FEE_HIGH = 10000;   // 1%

    // --- ARBITRAGE PARAMETERS (CUSTOMIZE THESE) ---
    const borrowAmount = ethers.utils.parseEther(process.env.BORROW_AMOUNT || "100");
    const minProfit = ethers.utils.parseEther(process.env.MIN_PROFIT || "0.5");
    const expectedProfit = ethers.utils.parseEther(process.env.EXPECTED_PROFIT || "2");
    const gasEstimate = parseInt(process.env.GAS_ESTIMATE || "350000");

    // --- STEP 1: ENCODE SWAP PATH ---
    const path = ethers.utils.solidityPack(
        ["address", "uint24", "address", "uint24", "address"],
        [WETH, FEE_MEDIUM, USDC, FEE_MEDIUM, WETH]
    );

    console.log("\n📊 Configuration:");
    console.log(`   Borrow Amount: ${ethers.utils.formatEther(borrowAmount)} WETH`);
    console.log(`   Min Profit: ${ethers.utils.formatEther(minProfit)} WETH`);
    console.log(`   Expected Profit: ${ethers.utils.formatEther(expectedProfit)} WETH`);
    console.log(`   Gas Estimate: ${gasEstimate} units`);

    // --- STEP 2: ENCODE UNISWAP V3 SWAP DATA ---
    const routerIface = new ethers.utils.Interface([
        "function exactInput((bytes path,address recipient,uint256 deadline,uint256 amountIn,uint256 amountOutMinimum)) returns (uint256)"
    ]);

    const deadline = Math.floor(Date.now() / 1000) + 1200; // 20 minutes

    const slippageTolerance = 50; // 0.5% in basis points
    const expectedOutput = borrowAmount.add(expectedProfit);
    const minAmountOut = expectedOutput.mul(10000 - slippageTolerance).div(10000);

    const swapData = routerIface.encodeFunctionData("exactInput", [{
        path,
        recipient: CONTRACT_ADDRESS,
        deadline,
        amountIn: borrowAmount,
        amountOutMinimum: minAmountOut
    }]);

    console.log("\n🔄 Swap Configuration:");
    console.log(`   Path: WETH → USDC → WETH`);
    console.log(`   Fee Tier: ${FEE_MEDIUM / 10000}%`);
    console.log(`   Slippage: ${slippageTolerance / 100}%`);
    console.log(`   Min Output: ${ethers.utils.formatEther(minAmountOut)} WETH`);
    console.log(`   Deadline: ${new Date(deadline * 1000).toLocaleString()}`);

    // --- STEP 3: CALCULATE PROFITABILITY ---
    const AAVE_V3_FEE_BPS = 5;
    const flashLoanFee = borrowAmount.mul(AAVE_V3_FEE_BPS).div(10000);

    const gasPrice = ethers.utils.parseUnits(process.env.GAS_PRICE || "50", "gwei");
    const gasCost = gasPrice.mul(gasEstimate);

    const slippageCost = borrowAmount.mul(slippageTolerance).div(10000);

    const totalCosts = flashLoanFee.add(gasCost).add(slippageCost);
    const netProfit = expectedProfit.sub(totalCosts);

    console.log("\n💰 Profitability Analysis:");
    console.log(`   Expected Gross Profit: ${ethers.utils.formatEther(expectedProfit)} WETH`);
    console.log(`   Flash Loan Fee (0.05%): ${ethers.utils.formatEther(flashLoanFee)} WETH`);
    console.log(`   Gas Cost (${ethers.utils.formatUnits(gasPrice, "gwei")} Gwei): ${ethers.utils.formatEther(gasCost)} ETH`);
    console.log(`   Slippage Cost (0.5%): ${ethers.utils.formatEther(slippageCost)} WETH`);
    console.log(`   ${"─".repeat(40)}`);
    console.log(`   Net Profit: ${ethers.utils.formatEther(netProfit)} WETH`);
    console.log(`   Profitable: ${netProfit.gt(0) ? "✅ YES" : "❌ NO"}`);

    const breakEvenCost = flashLoanFee.add(gasCost);
    const breakEvenBps = breakEvenCost.mul(10000).div(borrowAmount);
    console.log(`   Break-Even Spread: ${breakEvenBps.toNumber() / 100}%`);

    const roi = netProfit.mul(10000).div(borrowAmount);
    console.log(`   ROI: ${roi.toNumber() / 100}%`);

    // --- STEP 4: ENCODE ARBPLAN STRUCT ---
    const arbData = ethers.utils.defaultAbiCoder.encode(
        ["tuple(address routerAddress, bytes swapData, address finalToken, uint256 minProfit, uint256 expectedProfit, uint256 gasEstimate)"],
        [{
            routerAddress: UNI_V3_ROUTER,
            swapData,
            finalToken: WETH,
            minProfit,
            expectedProfit,
            gasEstimate
        }]
    );

    console.log("\n📦 Encoded Data:");
    console.log("=".repeat(80));
    console.log("\n✅ arbData (Paste this into Remix or use with Web3):");
    console.log(arbData);

    // --- STEP 5: GENERATE FUNCTION CALL INSTRUCTIONS ---
    console.log("\n🚀 Execution Instructions:");
    console.log("=".repeat(80));
    console.log("\n📋 Method 1: Using Remix");
    console.log(`\n1. Open your deployed contract in Remix`);
    console.log(`2. Call requestFlashLoan with:`);
    console.log(`   - loanAsset: ${WETH}`);
    console.log(`   - loanAmount: ${borrowAmount.toString()}`);
    console.log(`   - arbData: [See encoded data above]`);

    console.log("\n📋 Method 2: Using Python (Web3.py)");
    console.log(`
from web3 import Web3

contract_address = "${CONTRACT_ADDRESS}"
loan_asset = "${WETH}"
loan_amount = ${borrowAmount.toString()}
arb_data = "${arbData}"

tx = contract.functions.requestFlashLoan(
    loan_asset,
    loan_amount,
    arb_data
).transact({'from': your_address, 'gas': 500000})

print(f"Transaction hash: {tx.hex()}")
    `);

    // --- STEP 6: SAFETY CHECKS ---
    console.log("\n⚠️  Pre-Flight Checklist:");
    console.log("=".repeat(80));

    const checks = [
        { name: "Net profit is positive", passed: netProfit.gt(0), value: ethers.utils.formatEther(netProfit) + " WETH" },
        { name: "Net profit > min profit", passed: netProfit.gt(minProfit), value: `${ethers.utils.formatEther(netProfit)} > ${ethers.utils.formatEther(minProfit)}` },
        { name: "ROI > 1%", passed: roi.gt(100), value: `${roi.toNumber() / 100}%` },
        { name: "Gas price reasonable", passed: gasPrice.lte(ethers.utils.parseUnits("100", "gwei")), value: ethers.utils.formatUnits(gasPrice, "gwei") + " Gwei" },
        { name: "Contract address set", passed: CONTRACT_ADDRESS !== "0xYOUR_DEPLOYED_CONTRACT_ADDRESS", value: CONTRACT_ADDRESS },
        { name: "Deadline in future", passed: deadline > Math.floor(Date.now() / 1000), value: new Date(deadline * 1000).toLocaleString() }
    ];

    let allPassed = true;
    checks.forEach(check => {
        const status = check.passed ? "✅" : "❌";
        console.log(`${status} ${check.name}: ${check.value}`);
        if (!check.passed) allPassed = false;
    });

    console.log("\n" + "=".repeat(80));
    if (allPassed) {
        console.log("✅ ALL CHECKS PASSED - READY TO EXECUTE!");
        console.log("\n⚠️  WARNINGS:");
        console.log("   1. Test on testnet first!");
        console.log("   2. Verify liquidity in pools");
        console.log("   3. Check current gas prices");
        console.log("   4. Run simulateArbitrage() first");
    } else {
        console.log("❌ SOME CHECKS FAILED - REVIEW BEFORE EXECUTING!");
    }
    console.log("=".repeat(80));

    // --- RETURN STRUCTURED DATA ---
    return {
        config: {
            contractAddress: CONTRACT_ADDRESS,
            borrowAmount: borrowAmount.toString(),
            minProfit: minProfit.toString(),
            expectedProfit: expectedProfit.toString(),
            gasEstimate
        },
        encoded: {
            swapData,
            arbData
        },
        analysis: {
            flashLoanFee: flashLoanFee.toString(),
            gasCost: gasCost.toString(),
            netProfit: netProfit.toString(),
            roi: roi.toNumber(),
            breakEvenBps: breakEvenBps.toNumber()
        },
        execution: {
            loanAsset: WETH,
            loanAmount: borrowAmount.toString(),
            arbData
        }
    };
}

// Execute
if (require.main === module) {
    main()
        .then(result => {
            console.log("\n✅ Encoding complete!");
            process.exit(0);
        })
        .catch(error => {
            console.error("\n❌ Error:", error.message);
            process.exit(1);
        });
}

module.exports = { main };
