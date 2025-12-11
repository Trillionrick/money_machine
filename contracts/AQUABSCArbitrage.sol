// SPDX-License-Identifier: MIT
pragma solidity 0.8.25;

/**
 * @title AQUA BSC Flash Loan Arbitrage Contract
 * @notice High-frequency arbitrage for AQUA token using PancakeSwap V3 flash swaps
 * @dev Optimized for BSC with modern 2025 patterns - uses PancakeSwap V3 callback pattern
 * @author Money Machine - Advanced Arbitrage System
 */

// ========== INTERFACES ==========

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function decimals() external view returns (uint8);
}

/**
 * @dev AQUA Token Interface (Planet Finance Governance Token)
 * Contract: 0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991 (BSC BEP-20)
 */
interface IAQUA is IERC20 {
    function name() external view returns (string memory);
    function symbol() external view returns (string memory);
}

/**
 * @dev PancakeSwap V3 Pool Interface (for flash swaps)
 * Flash loan provider on BSC - no upfront fee, only pay on profit
 */
interface IPancakeV3Pool {
    function flash(
        address recipient,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external;

    function token0() external view returns (address);
    function token1() external view returns (address);
    function fee() external view returns (uint24);
}

/**
 * @dev PancakeSwap V3 Callback Interface
 */
interface IPancakeV3FlashCallback {
    function pancakeV3FlashCallback(
        uint256 fee0,
        uint256 fee1,
        bytes calldata data
    ) external;
}

/**
 * @dev PancakeSwap V3 Router Interface (for swaps)
 */
interface IPancakeV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params)
        external
        payable
        returns (uint256 amountOut);
}

/**
 * @dev Biswap V2 Router Interface (alternative DEX for arbitrage)
 */
interface IBiswapRouter {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);

    function getAmountsOut(uint256 amountIn, address[] calldata path)
        external
        view
        returns (uint256[] memory amounts);
}

// ========== MAIN CONTRACT ==========

contract AQUABSCArbitrage is IPancakeV3FlashCallback {

    // ========== STATE VARIABLES ==========

    address public immutable owner;

    // AQUA Token on BSC
    address public constant AQUA = 0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991;

    // Common base tokens on BSC
    address public constant WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;
    address public constant BUSD = 0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56;
    address public constant USDT = 0x55d398326f99059fF775485246999027B3197955;

    // PancakeSwap V3 addresses
    address public constant PANCAKE_V3_ROUTER = 0x13f4EA83D0bd40E75C8222255bc855a974568Dd4;
    address public constant PANCAKE_V3_FACTORY = 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865;

    // Alternative DEX for arbitrage (Biswap V2)
    address public constant BISWAP_ROUTER = 0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8;

    // Pool addresses (set by owner after deployment)
    address public aquaWbnbPoolPancake;    // AQUA/WBNB on PancakeSwap V3
    address public aquaWbnbPoolBiswap;     // AQUA/WBNB on Biswap V2

    // Configuration
    uint256 public minProfitBPS = 50;       // 0.5% minimum profit
    uint256 public maxGasPrice = 5 gwei;    // BSC typical gas: 3-5 gwei
    uint256 public slippageTolerance = 100; // 1% slippage tolerance

    uint256 public constant BPS_DENOMINATOR = 10000;
    uint256 public constant PANCAKE_V3_FEE_TIER = 2500; // 0.25% fee tier for AQUA pairs

    // Statistics
    uint256 public totalArbitrages;
    uint256 public totalProfit;
    uint256 public failedAttempts;

    // ========== STRUCTS ==========

    struct FlashParams {
        address tokenBorrow;     // Token to flash borrow (WBNB or BUSD)
        address tokenTarget;     // Token to arbitrage (AQUA)
        uint256 amountBorrow;    // Amount to borrow
        bool buyOnPancake;       // true: buy AQUA on Pancake, sell on Biswap
        uint256 minProfit;       // Minimum profit required
        address dexBuy;          // DEX to buy from
        address dexSell;         // DEX to sell on
    }

    struct ArbResult {
        uint256 borrowed;
        uint256 repaid;
        uint256 profit;
        uint256 gasUsed;
        bool success;
    }

    // ========== EVENTS ==========

    event ArbitrageExecuted(
        address indexed tokenBorrow,
        address indexed tokenTarget,
        uint256 amountBorrowed,
        uint256 profit,
        uint256 gasUsed,
        uint256 timestamp
    );

    event FlashLoanInitiated(
        address indexed pool,
        uint256 amount0,
        uint256 amount1
    );

    event ConfigUpdated(
        uint256 minProfitBPS,
        uint256 maxGasPrice,
        uint256 slippageTolerance
    );

    event PoolsConfigured(
        address pancakePool,
        address biswapPool
    );

    event EmergencyWithdrawal(
        address indexed token,
        uint256 amount
    );

    // ========== MODIFIERS ==========

    modifier onlyOwner() {
        require(msg.sender == owner, "AQUA: Only owner");
        _;
    }

    modifier gasOptimized() {
        require(tx.gasprice <= maxGasPrice, "AQUA: Gas price too high");
        _;
    }

    // ========== CONSTRUCTOR ==========

    constructor() {
        owner = msg.sender;
    }

    // ========== CONFIGURATION ==========

    /**
     * @notice Set pool addresses after deployment
     * @dev Owner must call this before executing arbitrages
     */
    function configurePools(
        address _aquaWbnbPoolPancake,
        address _aquaWbnbPoolBiswap
    ) external onlyOwner {
        require(_aquaWbnbPoolPancake != address(0), "AQUA: Invalid Pancake pool");
        require(_aquaWbnbPoolBiswap != address(0), "AQUA: Invalid Biswap pool");

        aquaWbnbPoolPancake = _aquaWbnbPoolPancake;
        aquaWbnbPoolBiswap = _aquaWbnbPoolBiswap;

        emit PoolsConfigured(_aquaWbnbPoolPancake, _aquaWbnbPoolBiswap);
    }

    function setMinProfitBPS(uint256 _minProfitBPS) external onlyOwner {
        require(_minProfitBPS >= 10 && _minProfitBPS <= 500, "AQUA: Invalid profit BPS");
        minProfitBPS = _minProfitBPS;
        emit ConfigUpdated(minProfitBPS, maxGasPrice, slippageTolerance);
    }

    function setMaxGasPrice(uint256 _maxGasPrice) external onlyOwner {
        require(_maxGasPrice > 0, "AQUA: Invalid gas price");
        maxGasPrice = _maxGasPrice;
        emit ConfigUpdated(minProfitBPS, maxGasPrice, slippageTolerance);
    }

    function setSlippageTolerance(uint256 _slippageTolerance) external onlyOwner {
        require(_slippageTolerance <= 500, "AQUA: Slippage too high");
        slippageTolerance = _slippageTolerance;
        emit ConfigUpdated(minProfitBPS, maxGasPrice, slippageTolerance);
    }

    // ========== MAIN ARBITRAGE FUNCTIONS ==========

    /**
     * @notice Execute AQUA arbitrage using flash loan
     * @dev Strategy: Borrow WBNB -> Buy AQUA on DEX1 -> Sell AQUA on DEX2 -> Repay + profit
     * @param borrowAmount Amount of WBNB to borrow
     * @param buyOnPancake true = buy on Pancake/sell on Biswap, false = reverse
     */
    function executeAQUAArbitrage(
        uint256 borrowAmount,
        bool buyOnPancake
    ) external onlyOwner gasOptimized {
        require(aquaWbnbPoolPancake != address(0), "AQUA: Pools not configured");
        require(borrowAmount > 0, "AQUA: Invalid borrow amount");

        // Prepare flash loan parameters
        FlashParams memory params = FlashParams({
            tokenBorrow: WBNB,
            tokenTarget: AQUA,
            amountBorrow: borrowAmount,
            buyOnPancake: buyOnPancake,
            minProfit: (borrowAmount * minProfitBPS) / BPS_DENOMINATOR,
            dexBuy: buyOnPancake ? PANCAKE_V3_ROUTER : BISWAP_ROUTER,
            dexSell: buyOnPancake ? BISWAP_ROUTER : PANCAKE_V3_ROUTER
        });

        bytes memory data = abi.encode(params);

        // Determine which token is token0/token1 in the pool
        IPancakeV3Pool pool = IPancakeV3Pool(aquaWbnbPoolPancake);
        address token0 = pool.token0();
        address token1 = pool.token1();

        uint256 amount0 = (token0 == WBNB) ? borrowAmount : 0;
        uint256 amount1 = (token1 == WBNB) ? borrowAmount : 0;

        emit FlashLoanInitiated(aquaWbnbPoolPancake, amount0, amount1);

        // Request flash loan from PancakeSwap V3
        pool.flash(address(this), amount0, amount1, data);
    }

    /**
     * @notice PancakeSwap V3 flash loan callback
     * @dev This is called by the pool after funds are sent
     */
    function pancakeV3FlashCallback(
        uint256 fee0,
        uint256 fee1,
        bytes calldata data
    ) external override {
        // Verify caller is a valid PancakeSwap V3 pool
        require(msg.sender == aquaWbnbPoolPancake, "AQUA: Unauthorized callback");

        uint256 gasStart = gasleft();

        FlashParams memory params = abi.decode(data, (FlashParams));

        // Calculate total amount owed (borrowed + fee)
        uint256 fee = (fee0 > 0) ? fee0 : fee1;
        uint256 amountOwed = params.amountBorrow + fee;

        // STEP 1: Buy AQUA on first DEX
        uint256 aquaReceived = _executeBuy(
            params.tokenBorrow,
            params.tokenTarget,
            params.amountBorrow,
            params.buyOnPancake
        );

        require(aquaReceived > 0, "AQUA: Buy failed");

        // STEP 2: Sell AQUA on second DEX
        uint256 wbnbReceived = _executeSell(
            params.tokenTarget,
            params.tokenBorrow,
            aquaReceived,
            !params.buyOnPancake
        );

        require(wbnbReceived >= amountOwed, "AQUA: Not profitable");

        uint256 profit = wbnbReceived - amountOwed;
        require(profit >= params.minProfit, "AQUA: Below min profit");

        // STEP 3: Repay flash loan
        IERC20(params.tokenBorrow).transfer(msg.sender, amountOwed);

        // STEP 4: Transfer profit to owner
        if (profit > 0) {
            IERC20(params.tokenBorrow).transfer(owner, profit);
        }

        // Update statistics
        totalArbitrages++;
        totalProfit += profit;

        uint256 gasUsed = gasStart - gasleft();

        emit ArbitrageExecuted(
            params.tokenBorrow,
            params.tokenTarget,
            params.amountBorrow,
            profit,
            gasUsed,
            block.timestamp
        );
    }

    // ========== INTERNAL SWAP FUNCTIONS ==========

    /**
     * @dev Execute buy on specified DEX
     */
    function _executeBuy(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        bool usePancake
    ) internal returns (uint256 amountOut) {
        if (usePancake) {
            return _buyOnPancakeV3(tokenIn, tokenOut, amountIn);
        } else {
            return _buyOnBiswap(tokenIn, tokenOut, amountIn);
        }
    }

    /**
     * @dev Execute sell on specified DEX
     */
    function _executeSell(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        bool usePancake
    ) internal returns (uint256 amountOut) {
        if (usePancake) {
            return _buyOnPancakeV3(tokenIn, tokenOut, amountIn);
        } else {
            return _buyOnBiswap(tokenIn, tokenOut, amountIn);
        }
    }

    /**
     * @dev Buy on PancakeSwap V3
     */
    function _buyOnPancakeV3(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) internal returns (uint256 amountOut) {
        IERC20(tokenIn).approve(PANCAKE_V3_ROUTER, amountIn);

        IPancakeV3Router.ExactInputSingleParams memory params = IPancakeV3Router.ExactInputSingleParams({
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            fee: PANCAKE_V3_FEE_TIER,
            recipient: address(this),
            amountIn: amountIn,
            amountOutMinimum: _calculateMinOut(amountIn),
            sqrtPriceLimitX96: 0
        });

        return IPancakeV3Router(PANCAKE_V3_ROUTER).exactInputSingle(params);
    }

    /**
     * @dev Buy on Biswap V2
     */
    function _buyOnBiswap(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) internal returns (uint256 amountOut) {
        IERC20(tokenIn).approve(BISWAP_ROUTER, amountIn);

        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;

        uint256 minOut = _calculateMinOut(amountIn);

        uint256[] memory amounts = IBiswapRouter(BISWAP_ROUTER).swapExactTokensForTokens(
            amountIn,
            minOut,
            path,
            address(this),
            block.timestamp + 300
        );

        return amounts[amounts.length - 1];
    }

    /**
     * @dev Calculate minimum output with slippage protection
     */
    function _calculateMinOut(uint256 amountIn) internal view returns (uint256) {
        return (amountIn * (BPS_DENOMINATOR - slippageTolerance)) / BPS_DENOMINATOR;
    }

    // ========== VIEW FUNCTIONS ==========

    /**
     * @notice Simulate arbitrage profitability
     * @dev Call this off-chain before executing to check if profitable
     */
    function simulateArbitrage(
        uint256 borrowAmount,
        bool buyOnPancake
    ) external view returns (
        uint256 estimatedProfit,
        uint256 estimatedAquaReceived,
        bool isProfitable
    ) {
        // This would require calling getAmountsOut on both DEXs
        // Implementation depends on having access to pool reserves
        // For now, return placeholder
        return (0, 0, false);
    }

    /**
     * @notice Get contract statistics
     */
    function getStats() external view returns (
        uint256 _totalArbitrages,
        uint256 _totalProfit,
        uint256 _failedAttempts
    ) {
        return (totalArbitrages, totalProfit, failedAttempts);
    }

    // ========== EMERGENCY FUNCTIONS ==========

    /**
     * @notice Withdraw tokens in case of emergency
     */
    function rescueFunds(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "AQUA: No balance");

        IERC20(token).transfer(owner, balance);
        emit EmergencyWithdrawal(token, balance);
    }

    /**
     * @notice Withdraw BNB
     */
    function rescueBNB() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "AQUA: No BNB balance");

        payable(owner).transfer(balance);
    }

    receive() external payable {}
}
