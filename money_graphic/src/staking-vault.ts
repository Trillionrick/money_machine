/**
 * StakingVault event handlers for The Graph.
 *
 * Captures stake/withdraw/reward flows while keeping vault state in sync
 * with the contract through safe try_* calls.
 *
 * @module staking-vault
 * @version 2.1.0
 */
import { BigInt, ethereum, log, Bytes } from "@graphprotocol/graph-ts";
import {
  RewardNotified as RewardNotifiedEvent,
  RewardPaid as RewardPaidEvent,
  Staked as StakedEvent,
  Withdrawn as WithdrawnEvent,
  StakingVault,
} from "../generated/StakingVault/StakingVault";
import {
  RewardNotification,
  RewardPaidAction,
  StakeAction,
  Vault,
  WithdrawAction,
} from "../generated/schema";

// ============================================================================
// Constants
// ============================================================================

/** BigInt representation of zero */
const ZERO_BI = BigInt.zero();

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Deterministic ID for entities created from events.
 */
function createEventId(event: ethereum.Event): Bytes {
  return event.transaction.hash.concatI32(event.logIndex.toI32());
}

/**
 * Refreshes mutable vault state that may change between events.
 *
 * Kept as a helper to avoid duplicating try_* calls across handlers.
 */
function hydrateVaultState(contract: StakingVault, vault: Vault): void {
  const rewardRateResult = contract.try_rewardRate();
  if (!rewardRateResult.reverted) {
    vault.rewardRate = rewardRateResult.value;
  } else {
    log.debug("Failed to fetch rewardRate for vault: {}", [
      contract._address.toHexString(),
    ]);
  }

  const periodFinishResult = contract.try_periodFinish();
  if (!periodFinishResult.reverted) {
    vault.periodFinish = periodFinishResult.value;
  } else {
    log.debug("Failed to fetch periodFinish for vault: {}", [
      contract._address.toHexString(),
    ]);
  }

  const lastUpdateResult = contract.try_lastUpdate();
  if (!lastUpdateResult.reverted) {
    vault.lastUpdate = lastUpdateResult.value;
  } else {
    log.debug("Failed to fetch lastUpdate for vault: {}", [
      contract._address.toHexString(),
    ]);
  }
}

/**
 * Ensures non-null defaults for vault numeric fields after hydration.
 */
function ensureVaultDefaults(vault: Vault): void {
  if (vault.rewardRate === null) {
    vault.rewardRate = ZERO_BI;
  }
  if (vault.periodFinish === null) {
    vault.periodFinish = ZERO_BI;
  }
  if (vault.lastUpdate === null) {
    vault.lastUpdate = ZERO_BI;
  }
}

/**
 * Loads or creates a Vault entity with current state from the smart contract.
 *
 * This function fetches the latest vault state including stake/reward tokens,
 * owner, reward rate, and period information. It safely handles contract
 * calls that may revert.
 *
 * @param event - Ethereum event containing vault address and block data
 * @returns Vault entity with updated state
 *
 * @remarks
 * - Always refreshes reward rate and period finish from contract
 * - Uses try_* calls to gracefully handle reverts
 * - Logs warnings when contract calls fail
 * - Updates last seen block and timestamp
 *
 * @example
 * ```typescript
 * const vault = getOrCreateVault(event);
 * log.info("Vault total staked: {}", [vault.totalStaked.toString()]);
 * ```
 */
function getOrCreateVault(event: ethereum.Event): Vault {
  let vault = Vault.load(event.address);
  const contract = StakingVault.bind(event.address);

  if (vault === null) {
    log.info("Creating new Vault entity for address: {}", [
      event.address.toHexString(),
    ]);

    vault = new Vault(event.address);

    // Fetch immutable vault configuration
    const stakeTokenResult = contract.try_stakeToken();
    if (!stakeTokenResult.reverted) {
      vault.stakeToken = stakeTokenResult.value;
    } else {
      log.warning("Failed to fetch stakeToken for vault: {}", [
        event.address.toHexString(),
      ]);
    }

    const rewardTokenResult = contract.try_rewardToken();
    if (!rewardTokenResult.reverted) {
      vault.rewardToken = rewardTokenResult.value;
    } else {
      log.warning("Failed to fetch rewardToken for vault: {}", [
        event.address.toHexString(),
      ]);
    }

    const ownerResult = contract.try_owner();
    if (!ownerResult.reverted) {
      vault.owner = ownerResult.value;
    } else {
      log.warning("Failed to fetch owner for vault: {}", [
        event.address.toHexString(),
      ]);
    }

    // Initialize mutable state
    vault.totalStaked = ZERO_BI;
    vault.rewardRate = ZERO_BI;
    vault.periodFinish = ZERO_BI;
    vault.lastUpdate = ZERO_BI;
    vault.lastUpdatedBlock = event.block.number;
    vault.lastUpdatedTimestamp = event.block.timestamp;

    log.info("Vault created successfully for address: {}", [
      event.address.toHexString(),
    ]);
  }

  hydrateVaultState(contract, vault);
  ensureVaultDefaults(vault);

  // Update metadata
  vault.lastUpdatedBlock = event.block.number;
  vault.lastUpdatedTimestamp = event.block.timestamp;

  return vault;
}

// ============================================================================
// Event Handlers
// ============================================================================

/**
 * Handles Staked events when users deposit tokens into the vault.
 *
 * Updates vault total staked amount and creates a StakeAction record
 * for tracking individual stake transactions.
 *
 * @param event - Staked event emitted when user stakes tokens
 *
 * @remarks
 * - Increments vault totalStaked by stake amount
 * - Creates indexed StakeAction entity for query/analytics
 * - Logs user, amount, and updated vault state
 *
 * @example
 * User stakes 1000 tokens → vault.totalStaked += 1000
 */
export function handleStaked(event: StakedEvent): void {
  log.info("Processing Staked event: user {} staked {}", [
    event.params.user.toHexString(),
    event.params.amount.toString(),
  ]);

  const vault = getOrCreateVault(event);

  // Update vault total
  vault.totalStaked = vault.totalStaked.plus(event.params.amount);
  vault.save();

  // Create stake action record
  const entity = new StakeAction(createEventId(event));

  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.amount = event.params.amount;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  log.info("Stake processed. Vault {} total staked: {}", [
    vault.id.toHexString(),
    vault.totalStaked.toString(),
  ]);
}

/**
 * Handles Withdrawn events when users remove tokens from the vault.
 *
 * Updates vault total staked amount and creates a WithdrawAction record
 * for tracking individual withdrawal transactions.
 *
 * @param event - Withdrawn event emitted when user withdraws tokens
 *
 * @remarks
 * - Decrements vault totalStaked by withdrawal amount
 * - Creates indexed WithdrawAction entity for query/analytics
 * - Logs user, amount, and updated vault state
 *
 * @example
 * User withdraws 500 tokens → vault.totalStaked -= 500
 */
export function handleWithdrawn(event: WithdrawnEvent): void {
  log.info("Processing Withdrawn event: user {} withdrew {}", [
    event.params.user.toHexString(),
    event.params.amount.toString(),
  ]);

  const vault = getOrCreateVault(event);

  // Update vault total
  const updatedStakeTotal = vault.totalStaked.minus(event.params.amount);
  vault.totalStaked = updatedStakeTotal.lt(ZERO_BI) ? ZERO_BI : updatedStakeTotal;
  vault.save();

  // Create withdrawal action record
  const entity = new WithdrawAction(createEventId(event));

  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.amount = event.params.amount;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  log.info("Withdrawal processed. Vault {} total staked: {}", [
    vault.id.toHexString(),
    vault.totalStaked.toString(),
  ]);
}

/**
 * Handles RewardPaid events when rewards are distributed to users.
 *
 * Creates a RewardPaidAction record for tracking reward payments.
 * Does not modify vault totals (handled by contract).
 *
 * @param event - RewardPaid event emitted when user claims rewards
 *
 * @remarks
 * - Creates indexed RewardPaidAction entity for analytics
 * - Refreshes vault state to capture any contract changes
 * - Logs user and reward amount
 *
 * @example
 * User claims 50 reward tokens → RewardPaidAction created
 */
export function handleRewardPaid(event: RewardPaidEvent): void {
  log.info("Processing RewardPaid event: user {} received reward {}", [
    event.params.user.toHexString(),
    event.params.reward.toString(),
  ]);

  const vault = getOrCreateVault(event);
  vault.save();

  // Create reward payment record
  const entity = new RewardPaidAction(createEventId(event));

  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.reward = event.params.reward;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  log.info("Reward payment processed for user: {}", [
    event.params.user.toHexString(),
  ]);
}

/**
 * Handles RewardNotified events when new rewards are added to the vault.
 *
 * Updates vault reward distribution parameters and creates a notification
 * record for tracking reward additions over time.
 *
 * @param event - RewardNotified event emitted when rewards are deposited
 *
 * @remarks
 * - Refreshes vault rewardRate and periodFinish from contract
 * - Creates indexed RewardNotification entity
 * - Logs reward amount and distribution duration
 * - Critical for APY calculations and reward analytics
 *
 * @example
 * 10,000 tokens added over 7 days → rewardRate = 10000/604800 per second
 */
export function handleRewardNotified(event: RewardNotifiedEvent): void {
  log.info("Processing RewardNotified event: {} tokens over {} seconds", [
    event.params.amount.toString(),
    event.params.duration.toString(),
  ]);

  const vault = getOrCreateVault(event);
  const contract = StakingVault.bind(event.address);

  hydrateVaultState(contract, vault);

  vault.lastUpdatedBlock = event.block.number;
  vault.lastUpdatedTimestamp = event.block.timestamp;
  vault.save();

  // Create reward notification record
  const entity = new RewardNotification(createEventId(event));

  entity.vault = vault.id;
  entity.amount = event.params.amount;
  entity.duration = event.params.duration;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  log.info("Reward notification processed. New rate: {}, finish: {}", [
    vault.rewardRate.toString(),
    vault.periodFinish.toString(),
  ]);
}
