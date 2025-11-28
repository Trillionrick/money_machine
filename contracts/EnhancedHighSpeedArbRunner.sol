// SPDX-License-Identifier: MIT
pragma solidity 0.8.25;

/**
 * @title EnhancedHighSpeedArbRunner (Stack-Optimized)
 * @notice Advanced Flash Loan Arbitrage Contract - Optimized to avoid "Stack Too Deep" errors
 * @dev This version reduces local variables by using helper functions and structs
 */

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function decimals() external view returns (uint8);
}

interface IAavePool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IFlashLoanReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IUniswapV2Pair {
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast);
    function token0() external view returns (address);
    function token1() external view returns (address);
}

contract EnhancedHighSpeedArbRunner is IFlashLoanReceiver {
    // ========== CONSTANTS & IMMUTABLES ==========

    address public immutable AAVE_POOL;
    address public immutable UNI_V3_ROUTER;
    address public immutable WETH;

    uint256 public constant AAVE_V3_FLASH_FEE_BPS = 5;
    uint256 public constant BPS_DENOMINATOR = 10000;
    uint256 public constant MIN_PROFIT_MARGIN_BPS = 10;

    uint256 public maxGasPrice = 100 gwei;
    uint256 public slippageTolerance = 50;

    address public owner;

    // ========== STRUCTS ==========

    struct ArbPlan {
        address routerAddress;
        bytes swapData;
        address finalToken;
        uint256 minProfit;
        uint256 expectedProfit;
        uint256 gasEstimate;
    }

    struct MultiHopPath {
        address[] tokens;
        address[] routers;
        uint24[] fees;
        uint256 amountIn;
        uint256 expectedOut;
    }

    struct ProfitabilityCheck {
        uint256 grossProfit;
        uint256 flashLoanFee;
        uint256 gasCost;
        uint256 slippageCost;
        uint256 netProfit;
        bool isProfitable;
    }

    struct AMMReserves {
        uint256 reserve0;
        uint256 reserve1;
        address token0;
        address token1;
    }

    // NEW: Struct to reduce stack depth in executeOperation
    struct ExecutionContext {
        uint256 gasStart;
        uint256 amountOwed;
        uint256 finalBalance;
        uint256 actualProfit;
        uint256 gasUsed;
        uint256 gasCost;
    }

    // ========== EVENTS ==========

    event ArbitrageExecuted(
        address indexed asset,
        uint256 borrowAmount,
        uint256 profit,
        uint256 gasCost,
        uint256 timestamp
    );

    event ProfitabilityAnalysis(
        uint256 grossProfit,
        uint256 flashLoanFee,
        uint256 gasCost,
        uint256 netProfit,
        bool approved
    );

    event FlashLoanInitiated(
        address indexed asset,
        uint256 amount,
        uint256 estimatedProfit
    );

    event ConfigUpdated(
        uint256 maxGasPrice,
        uint256 slippageTolerance
    );

    event EmergencyWithdrawal(
        address indexed token,
        uint256 amount,
        address indexed to
    );

    // ========== MODIFIERS ==========

    modifier onlyOwner() {
        require(msg.sender == owner, "HSA: Only owner");
        _;
    }

    modifier gasOptimized() {
        require(tx.gasprice <= maxGasPrice, "HSA: Gas price too high");
        _;
    }

    // ========== CONSTRUCTOR ==========

    constructor(
        address _aavePool,
        address _uniV3Router,
        address _weth
    ) {
        require(_aavePool != address(0), "HSA: Invalid Aave pool");
        require(_uniV3Router != address(0), "HSA: Invalid router");
        require(_weth != address(0), "HSA: Invalid WETH");

        owner = msg.sender;
        AAVE_POOL = _aavePool;
        UNI_V3_ROUTER = _uniV3Router;
        WETH = _weth;
    }

    // ========== CORE ARBITRAGE FUNCTIONS ==========

    function requestFlashLoan(
        address loanAsset,
        uint256 loanAmount,
        bytes calldata arbData
    ) external onlyOwner gasOptimized {
        ArbPlan memory plan = _decodePlan(arbData);

        ProfitabilityCheck memory check = calculateProfitability(
            loanAmount,
            plan.expectedProfit,
            plan.gasEstimate
        );

        emit ProfitabilityAnalysis(
            check.grossProfit,
            check.flashLoanFee,
            check.gasCost,
            check.netProfit,
            check.isProfitable
        );

        require(check.isProfitable, "HSA: Not profitable");
        require(check.netProfit >= plan.minProfit, "HSA: Below min profit threshold");

        emit FlashLoanInitiated(loanAsset, loanAmount, check.netProfit);

        IAavePool(AAVE_POOL).flashLoanSimple(
            address(this),
            loanAsset,
            loanAmount,
            arbData,
            0
        );
    }

    /**
     * @notice Optimized executeOperation - Reduced local variables
     * @dev Uses struct and helper functions to avoid stack too deep
     */
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address, // initiator
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == AAVE_POOL, "HSA: Unauthorized caller");

        // Use struct to reduce stack depth
        ExecutionContext memory ctx;
        ctx.gasStart = gasleft();

        ArbPlan memory plan = _decodePlan(params);
        require(plan.finalToken == asset, "HSA: Token mismatch");

        ctx.amountOwed = amount + premium;

        // Execute the swap
        _executeSwap(asset, amount, plan.routerAddress, plan.swapData);

        // Validate profit and repay
        ctx.finalBalance = IERC20(asset).balanceOf(address(this));
        _validateAndRepay(asset, ctx.amountOwed, ctx.finalBalance, amount, plan.minProfit);

        // Calculate metrics
        ctx.actualProfit = ctx.finalBalance - ctx.amountOwed;
        ctx.gasUsed = ctx.gasStart - gasleft();
        ctx.gasCost = ctx.gasUsed * tx.gasprice;

        emit ArbitrageExecuted(
            asset,
            amount,
            ctx.actualProfit,
            ctx.gasCost,
            block.timestamp
        );

        return true;
    }

    // ========== INTERNAL HELPER FUNCTIONS (Reduce Stack Depth) ==========

    /**
     * @dev Execute swap - extracted to reduce stack depth
     */
    function _executeSwap(
        address asset,
        uint256 amount,
        address router,
        bytes memory swapData
    ) internal {
        _approveToken(asset, router, amount);

        (bool success, bytes memory returnData) = router.call(swapData);
        require(success, _getRevertMsg(returnData));
    }

    /**
     * @dev Validate profit and repay loan - extracted to reduce stack depth
     */
    function _validateAndRepay(
        address asset,
        uint256 amountOwed,
        uint256 finalBalance,
        uint256 borrowAmount,
        uint256 minProfit
    ) internal {
        require(finalBalance > amountOwed, "HSA: Loss detected");

        uint256 minProfitWithMargin = _calculateMinProfitWithMargin(borrowAmount, minProfit);
        require(
            finalBalance >= amountOwed + minProfitWithMargin,
            "HSA: Insufficient profit margin"
        );

        _approveToken(asset, AAVE_POOL, amountOwed);
    }

    // ========== PROFITABILITY CALCULATIONS ==========

    function calculateProfitability(
        uint256 borrowAmount,
        uint256 expectedGrossProfit,
        uint256 gasEstimate
    ) public view returns (ProfitabilityCheck memory check) {
        check.flashLoanFee = (borrowAmount * AAVE_V3_FLASH_FEE_BPS) / BPS_DENOMINATOR;
        check.gasCost = gasEstimate * tx.gasprice;
        check.slippageCost = (borrowAmount * slippageTolerance) / BPS_DENOMINATOR;
        check.grossProfit = expectedGrossProfit;

        uint256 totalCosts = check.flashLoanFee + check.gasCost + check.slippageCost;

        if (check.grossProfit > totalCosts) {
            check.netProfit = check.grossProfit - totalCosts;
            check.isProfitable = true;
        } else {
            check.netProfit = 0;
            check.isProfitable = false;
        }

        return check;
    }

    function getAmountOut(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint256 poolFeeBps
    ) public pure returns (uint256 amountOut) {
        require(amountIn > 0, "HSA: Insufficient input");
        require(reserveIn > 0 && reserveOut > 0, "HSA: Insufficient liquidity");

        uint256 amountInWithFee = amountIn * (BPS_DENOMINATOR - poolFeeBps);
        uint256 numerator = reserveOut * amountInWithFee;
        uint256 denominator = (reserveIn * BPS_DENOMINATOR) + amountInWithFee;

        amountOut = numerator / denominator;
        return amountOut;
    }

    function calculatePriceImpact(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint256 poolFeeBps
    ) public pure returns (uint256 priceImpactBps) {
        uint256 initialPrice = (reserveOut * BPS_DENOMINATOR) / reserveIn;
        uint256 amountOut = getAmountOut(reserveIn, reserveOut, amountIn, poolFeeBps);

        if (amountOut == 0) return BPS_DENOMINATOR;

        uint256 avgExecutionPrice = (amountOut * BPS_DENOMINATOR) / amountIn;

        if (avgExecutionPrice >= initialPrice) return 0;

        priceImpactBps = ((initialPrice - avgExecutionPrice) * BPS_DENOMINATOR) / initialPrice;
        return priceImpactBps;
    }

    function simulateArbitrage(
        address pairAddress1,
        address pairAddress2,
        uint256 borrowAmount,
        bool zeroForOne
    ) external view returns (
        uint256 expectedProfit,
        uint256 priceImpact1,
        uint256 priceImpact2,
        bool isProfitable
    ) {
        AMMReserves memory reserves1 = _getReserves(pairAddress1);
        AMMReserves memory reserves2 = _getReserves(pairAddress2);

        uint256 amountOut1 = getAmountOut(
            zeroForOne ? reserves1.reserve0 : reserves1.reserve1,
            zeroForOne ? reserves1.reserve1 : reserves1.reserve0,
            borrowAmount,
            30
        );

        uint256 amountOut2 = getAmountOut(
            zeroForOne ? reserves2.reserve1 : reserves2.reserve0,
            zeroForOne ? reserves2.reserve0 : reserves2.reserve1,
            amountOut1,
            30
        );

        if (amountOut2 > borrowAmount) {
            expectedProfit = amountOut2 - borrowAmount;
            uint256 flashFee = (borrowAmount * AAVE_V3_FLASH_FEE_BPS) / BPS_DENOMINATOR;
            isProfitable = expectedProfit > flashFee;
        }

        priceImpact1 = calculatePriceImpact(
            zeroForOne ? reserves1.reserve0 : reserves1.reserve1,
            zeroForOne ? reserves1.reserve1 : reserves1.reserve0,
            borrowAmount,
            30
        );

        priceImpact2 = calculatePriceImpact(
            zeroForOne ? reserves2.reserve1 : reserves2.reserve0,
            zeroForOne ? reserves2.reserve0 : reserves2.reserve1,
            amountOut1,
            30
        );

        return (expectedProfit, priceImpact1, priceImpact2, isProfitable);
    }

    function calculateBreakEvenSpread(
        uint256 borrowAmount,
        uint256 gasEstimate
    ) public view returns (uint256 breakEvenBps) {
        uint256 flashFee = (borrowAmount * AAVE_V3_FLASH_FEE_BPS) / BPS_DENOMINATOR;
        uint256 gasCost = gasEstimate * tx.gasprice;
        uint256 totalCost = flashFee + gasCost;

        breakEvenBps = (totalCost * BPS_DENOMINATOR) / borrowAmount;
        return breakEvenBps;
    }

    function calculateRAAV(
        uint256 netProfit,
        uint256 gasCost,
        uint256 failureProbabilityBps
    ) public pure returns (uint256 raav) {
        uint256 expectedLoss = (gasCost * failureProbabilityBps) / BPS_DENOMINATOR;

        if (netProfit > expectedLoss) {
            raav = netProfit - expectedLoss;
        } else {
            raav = 0;
        }

        return raav;
    }

    // ========== MULTI-HOP SUPPORT ==========

    function executeMultiHop(
        MultiHopPath memory path
    ) internal returns (uint256 finalAmount) {
        require(path.tokens.length >= 2, "HSA: Invalid path length");
        require(path.tokens.length == path.routers.length + 1, "HSA: Path/router mismatch");

        uint256 currentAmount = path.amountIn;

        for (uint256 i = 0; i < path.routers.length; i++) {
            address tokenIn = path.tokens[i];
            address tokenOut = path.tokens[i + 1];
            address router = path.routers[i];

            _approveToken(tokenIn, router, currentAmount);
            currentAmount = IERC20(tokenOut).balanceOf(address(this));
        }

        return currentAmount;
    }

    // ========== CONFIGURATION ==========

    function setMaxGasPrice(uint256 _maxGasPrice) external onlyOwner {
        require(_maxGasPrice > 0, "HSA: Invalid gas price");
        maxGasPrice = _maxGasPrice;
        emit ConfigUpdated(maxGasPrice, slippageTolerance);
    }

    function setSlippageTolerance(uint256 _slippageTolerance) external onlyOwner {
        require(_slippageTolerance <= 500, "HSA: Slippage too high");
        slippageTolerance = _slippageTolerance;
        emit ConfigUpdated(maxGasPrice, slippageTolerance);
    }

    function rescueFunds(address token, uint256 amount) external onlyOwner {
        IERC20(token).transfer(owner, amount);
        emit EmergencyWithdrawal(token, amount, owner);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "HSA: Invalid owner");
        owner = newOwner;
    }

    // ========== INTERNAL UTILITIES ==========

    function _decodePlan(bytes memory data) internal pure returns (ArbPlan memory) {
        return abi.decode(data, (ArbPlan));
    }

    function _approveToken(address token, address spender, uint256 amount) internal {
        IERC20(token).approve(spender, amount);
    }

    function _calculateMinProfitWithMargin(
        uint256 borrowAmount,
        uint256 minProfit
    ) internal pure returns (uint256) {
        uint256 safetyMargin = (borrowAmount * MIN_PROFIT_MARGIN_BPS) / BPS_DENOMINATOR;
        return minProfit + safetyMargin;
    }

    function _getReserves(address pairAddress) internal view returns (AMMReserves memory reserves) {
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);
        (uint112 reserve0, uint112 reserve1,) = pair.getReserves();

        reserves.reserve0 = uint256(reserve0);
        reserves.reserve1 = uint256(reserve1);
        reserves.token0 = pair.token0();
        reserves.token1 = pair.token1();

        return reserves;
    }

    function _getRevertMsg(bytes memory returnData) internal pure returns (string memory) {
        if (returnData.length < 68) return "HSA: Swap failed";

        assembly {
            returnData := add(returnData, 0x04)
        }

        return abi.decode(returnData, (string));
    }

    receive() external payable {}
}
