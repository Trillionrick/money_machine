/**
 * GrowDollar token handlers for The Graph (2025-ready).
 *
 * Observes ERC-20 approvals and transfers to maintain token metadata,
 * holder balances, and daily activity snapshots with defensive handling
 * for reverts and zero-address mint/burn flows.
 */
import { Address, BigInt, Bytes, ethereum, log } from "@graphprotocol/graph-ts";
import {
  Approval as ApprovalEvent,
  Transfer as TransferEvent,
  GrowDollar,
} from "../generated/GrowDollar/GrowDollar";
import {
  Approval,
  Transfer,
  Token,
  HolderBalance,
  DailySnapshot,
} from "../generated/schema";

// ============================================================================
// Constants
// ============================================================================

/** Zero address (0x0000...0000) used for mint/burn detection */
const ZERO_ADDRESS = Address.zero();

/** BigInt representation of zero */
const ZERO_BI = BigInt.zero();

/** Seconds per day for daily snapshot calculations */
const SECONDS_PER_DAY = 86400;

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Creates a deterministic ID for any event-backed entity.
 *
 * Using a shared helper avoids duplicated logic and keeps entity IDs
 * stable even if handlers are refactored.
 */
function createEventId(event: ethereum.Event): Bytes {
  return event.transaction.hash.concatI32(event.logIndex.toI32());
}

/**
 * Normalizes a timestamp into a day-based bucket ID.
 */
function dayId(timestamp: BigInt): i32 {
  return timestamp.toI32() / SECONDS_PER_DAY;
}

/**
 * Loads or creates a Token entity for tracking token metadata and statistics.
 *
 * This function attempts to load an existing Token entity from the store.
 * If none exists, it creates a new one and populates it with data from the
 * smart contract using try_* calls for safety.
 *
 * @param event - Ethereum event containing token address and block data
 * @returns Token entity (either loaded or newly created)
 *
 * @remarks
 * - Uses try_* contract calls to handle potential reverts gracefully
 * - Initializes holder count to 0 for new tokens
 * - Updates last seen block and timestamp
 */
function getOrCreateToken(event: ethereum.Event): Token {
  let token = Token.load(event.address);

  if (token === null) {
    log.info("Creating new Token entity for address: {}", [
      event.address.toHexString(),
    ]);

    token = new Token(event.address);
    const contract = GrowDollar.bind(event.address);

    // Safely fetch token metadata
    const nameResult = contract.try_name();
    if (!nameResult.reverted) {
      token.name = nameResult.value;
    } else {
      log.warning("Failed to fetch name for token: {}", [
        event.address.toHexString(),
      ]);
    }

    const symbolResult = contract.try_symbol();
    if (!symbolResult.reverted) {
      token.symbol = symbolResult.value;
    } else {
      log.warning("Failed to fetch symbol for token: {}", [
        event.address.toHexString(),
      ]);
    }

    const decimalsResult = contract.try_decimals();
    if (!decimalsResult.reverted) {
      token.decimals = decimalsResult.value;
    } else {
      log.warning("Failed to fetch decimals for token: {}", [
        event.address.toHexString(),
      ]);
    }

    const supplyResult = contract.try_totalSupply();
    token.totalSupply = supplyResult.reverted ? ZERO_BI : supplyResult.value;

    // Initialize counters
    token.holderCount = 0;
    token.transferCount = 0;
    token.totalVolume = ZERO_BI;
    token.lastUpdatedBlock = event.block.number;
    token.lastUpdatedTimestamp = event.block.timestamp;

    log.info("Token created successfully: {} ({})", [
      token.symbol,
      event.address.toHexString(),
    ]);
  }

  // Backfill any newly added counters if upgrading an existing entity
  if (token.transferCount === null) {
    token.transferCount = 0;
  }
  if (token.totalVolume === null) {
    token.totalVolume = ZERO_BI;
  }

  return token;
}

/**
 * Generates a unique ID for a holder balance entity.
 *
 * @param token - Token contract address
 * @param holder - Holder wallet address
 * @returns Unique string ID in format: "token-holder"
 *
 * @example
 * ```typescript
 * const id = balanceId(tokenBytes, holderAddr);
 * // Returns: "0x1234...abcd-0x5678...ef00"
 * ```
 */
function balanceId(token: Bytes, holder: Address): string {
  return token.toHexString() + "-" + holder.toHexString();
}

/**
 * Loads or creates a HolderBalance entity for tracking individual balances.
 *
 * @param token - Token entity the balance is associated with
 * @param holder - Address of the token holder
 * @param block - Current block for timestamp tracking
 * @returns HolderBalance entity (either loaded or newly created)
 *
 * @remarks
 * - New balances start at zero
 * - Tracks first seen block for historical analysis
 * - Updates last seen block and timestamp on every access
 */
function getOrCreateBalance(
  token: Token,
  holder: Address,
  block: ethereum.Block
): HolderBalance {
  const id = balanceId(token.id, holder);
  let balance = HolderBalance.load(id);

  if (balance === null) {
    log.debug("Creating new HolderBalance for token {} and holder {}", [
      token.id.toHexString(),
      holder.toHexString(),
    ]);

    balance = new HolderBalance(id);
    balance.holder = holder;
    balance.token = token.id;
    balance.balance = ZERO_BI;
    balance.firstSeenBlock = block.number;
  }

  balance.lastUpdatedBlock = block.number;
  balance.lastUpdatedTimestamp = block.timestamp;

  return balance;
}

/**
 * Updates or creates a daily snapshot of token activity.
 *
 * Daily snapshots aggregate transfer counts, volume, holder counts,
 * and total supply for time-series analysis.
 *
 * @param token - Token entity to snapshot
 * @param event - Transfer event containing block data
 * @param amount - Transfer amount to add to daily volume
 *
 * @remarks
 * - Snapshots are keyed by token address and day number (Unix timestamp / 86400)
 * - Accumulates transfer count and volume throughout the day
 * - Captures point-in-time holder count and total supply
 */
function updateDailySnapshot(
  token: Token,
  event: TransferEvent,
  amount: BigInt
): void {
  const day = dayId(event.block.timestamp);
  const id = token.id.toHexString() + "-" + day.toString();

  let snapshot = DailySnapshot.load(id);

  if (snapshot === null) {
    log.debug("Creating new DailySnapshot for token {} on day {}", [
      token.id.toHexString(),
      day.toString(),
    ]);

    snapshot = new DailySnapshot(id);
    snapshot.token = token.id;
    snapshot.date = day;
    snapshot.transferCount = 0;
    snapshot.volume = ZERO_BI;
  }

  // Accumulate daily statistics
  snapshot.transferCount = snapshot.transferCount + 1;
  snapshot.volume = snapshot.volume.plus(amount);
  snapshot.holderCount = token.holderCount;
  snapshot.totalSupply = token.totalSupply;
  snapshot.blockNumber = event.block.number;
  snapshot.blockTimestamp = event.block.timestamp;

  snapshot.save();
}

// ============================================================================
// Event Handlers
// ============================================================================

/**
 * Handles ERC20 Approval events.
 *
 * Records approval events where an owner grants permission to a spender
 * to transfer tokens on their behalf.
 *
 * @param event - Approval event emitted by the token contract
 *
 * @remarks
 * - Creates an Approval entity for each event
 * - Indexed by transaction hash + log index for uniqueness
 * - Captures owner, spender, amount, block, and transaction data
 */
export function handleApproval(event: ApprovalEvent): void {
  log.debug("Processing Approval event: {} approves {} to spend {}", [
    event.params.owner.toHexString(),
    event.params.spender.toHexString(),
    event.params.value.toString(),
  ]);

  const entity = new Approval(createEventId(event));

  entity.owner = event.params.owner;
  entity.spender = event.params.spender;
  entity.value = event.params.value;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  log.debug("Approval entity persisted with id {}", [entity.id.toHexString()]);
}

/**
 * Handles ERC20 Transfer events.
 *
 * This is the main handler that tracks:
 * - Token transfers between addresses
 * - Mints (from 0x0) and burns (to 0x0)
 * - Holder balance updates
 * - Holder count changes
 * - Total supply changes
 * - Daily activity snapshots
 *
 * @param event - Transfer event emitted by the token contract
 *
 * @remarks
 * - Updates sender and receiver balances
 * - Increments holder count when new non-zero balance created
 * - Decrements holder count when balance reaches zero
 * - Updates total supply for mints and burns
 * - Creates daily snapshot entry
 *
 * @example
 * Mint: Transfer(0x0, userA, 100) → totalSupply +100, holderCount +1
 * Transfer: Transfer(userA, userB, 50) → balances updated, holderCount unchanged
 * Burn: Transfer(userA, 0x0, 50) → totalSupply -50, possibly holderCount -1
 */
export function handleTransfer(event: TransferEvent): void {
  log.info("Processing Transfer: {} → {} (amount: {})", [
    event.params.from.toHexString(),
    event.params.to.toHexString(),
    event.params.value.toString(),
  ]);

  // Create Transfer entity
  const entity = new Transfer(createEventId(event));

  entity.from = event.params.from;
  entity.to = event.params.to;
  entity.value = event.params.value;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;

  entity.save();

  // Update token state
  const token = getOrCreateToken(event);
  const amount = event.params.value;
  const fromIsZero = event.params.from.equals(ZERO_ADDRESS);
  const toIsZero = event.params.to.equals(ZERO_ADDRESS);

  token.transferCount = token.transferCount + 1;
  token.totalVolume = token.totalVolume.plus(amount);

  // Update sender balance (if not mint)
  if (!fromIsZero) {
    const fromBalance = getOrCreateBalance(token, event.params.from, event.block);
    const wasPositive = fromBalance.balance.gt(ZERO_BI);

    fromBalance.balance = fromBalance.balance.minus(amount);
    fromBalance.save();

    // Decrement holder count if balance went to zero
    if (wasPositive && fromBalance.balance.equals(ZERO_BI)) {
      token.holderCount = token.holderCount > 0 ? token.holderCount - 1 : 0;
      log.debug("Holder count decreased to {} (address: {})", [
        token.holderCount.toString(),
        event.params.from.toHexString(),
      ]);
    }
  }

  // Update receiver balance (if not burn)
  if (!toIsZero) {
    const toBalance = getOrCreateBalance(token, event.params.to, event.block);
    const wasZero = toBalance.balance.equals(ZERO_BI);

    toBalance.balance = toBalance.balance.plus(amount);
    toBalance.save();

    // Increment holder count if this is a new holder
    if (wasZero && toBalance.balance.gt(ZERO_BI)) {
      token.holderCount = token.holderCount + 1;
      log.debug("Holder count increased to {} (new address: {})", [
        token.holderCount.toString(),
        event.params.to.toHexString(),
      ]);
    }
  }

  // Update total supply
  if (fromIsZero && !toIsZero) {
    // Mint
    token.totalSupply = token.totalSupply.plus(amount);
    log.info("Mint detected: total supply now {}", [token.totalSupply.toString()]);
  } else if (toIsZero && !fromIsZero) {
    // Burn
    token.totalSupply = token.totalSupply.minus(amount);
    if (token.totalSupply.lt(ZERO_BI)) {
      token.totalSupply = ZERO_BI;
    }
    log.info("Burn detected: total supply now {}", [token.totalSupply.toString()]);
  }

  // Update token metadata
  token.lastUpdatedBlock = event.block.number;
  token.lastUpdatedTimestamp = event.block.timestamp;
  token.save();

  // Update daily snapshot
  updateDailySnapshot(token, event, amount);

  log.info("Transfer processed successfully. Token state: holders={}, supply={}", [
    token.holderCount.toString(),
    token.totalSupply.toString(),
  ]);
}
