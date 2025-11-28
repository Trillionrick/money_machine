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
import { BigInt, ethereum } from "@graphprotocol/graph-ts";

const ZERO_BI = BigInt.zero();

function getOrCreateVault(event: ethereum.Event): Vault {
  let vault = Vault.load(event.address);
  if (vault == null) {
    let contract = StakingVault.bind(event.address);
    vault = new Vault(event.address);

    let stakeTokenResult = contract.try_stakeToken();
    if (!stakeTokenResult.reverted) {
      vault.stakeToken = stakeTokenResult.value;
    }

    let rewardTokenResult = contract.try_rewardToken();
    if (!rewardTokenResult.reverted) {
      vault.rewardToken = rewardTokenResult.value;
    }

    let ownerResult = contract.try_owner();
    if (!ownerResult.reverted) {
      vault.owner = ownerResult.value;
    }

    vault.totalStaked = ZERO_BI;
    vault.rewardRate = ZERO_BI;
    vault.periodFinish = ZERO_BI;
    vault.lastUpdate = ZERO_BI;
    vault.lastUpdatedBlock = event.block.number;
    vault.lastUpdatedTimestamp = event.block.timestamp;
  }

  let contract = StakingVault.bind(event.address);
  let rewardRateResult = contract.try_rewardRate();
  if (!rewardRateResult.reverted) {
    vault.rewardRate = rewardRateResult.value;
  }

  let periodFinishResult = contract.try_periodFinish();
  if (!periodFinishResult.reverted) {
    vault.periodFinish = BigInt.fromString(periodFinishResult.value.toString());
  }

  let lastUpdateResult = contract.try_lastUpdate();
  if (!lastUpdateResult.reverted) {
    vault.lastUpdate = BigInt.fromString(lastUpdateResult.value.toString());
  }

  vault.lastUpdatedBlock = event.block.number;
  vault.lastUpdatedTimestamp = event.block.timestamp;

  return vault as Vault;
}

export function handleStaked(event: StakedEvent): void {
  let vault = getOrCreateVault(event);

  vault.totalStaked = vault.totalStaked.plus(event.params.amount);
  vault.save();

  let entity = new StakeAction(
    event.transaction.hash.concatI32(event.logIndex.toI32()),
  );
  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.amount = event.params.amount;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;
  entity.save();
}

export function handleWithdrawn(event: WithdrawnEvent): void {
  let vault = getOrCreateVault(event);

  vault.totalStaked = vault.totalStaked.minus(event.params.amount);
  vault.save();

  let entity = new WithdrawAction(
    event.transaction.hash.concatI32(event.logIndex.toI32()),
  );
  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.amount = event.params.amount;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;
  entity.save();
}

export function handleRewardPaid(event: RewardPaidEvent): void {
  let vault = getOrCreateVault(event);
  vault.save();

  let entity = new RewardPaidAction(
    event.transaction.hash.concatI32(event.logIndex.toI32()),
  );
  entity.vault = vault.id;
  entity.user = event.params.user;
  entity.reward = event.params.reward;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;
  entity.save();
}

export function handleRewardNotified(event: RewardNotifiedEvent): void {
  let vault = getOrCreateVault(event);
  let contract = StakingVault.bind(event.address);

  let rewardRateResult = contract.try_rewardRate();
  if (!rewardRateResult.reverted) {
    vault.rewardRate = rewardRateResult.value;
  }

  let periodFinishResult = contract.try_periodFinish();
  if (!periodFinishResult.reverted) {
    vault.periodFinish = BigInt.fromString(periodFinishResult.value.toString());
  }

  vault.lastUpdatedBlock = event.block.number;
  vault.lastUpdatedTimestamp = event.block.timestamp;
  vault.save();

  let entity = new RewardNotification(
    event.transaction.hash.concatI32(event.logIndex.toI32()),
  );
  entity.vault = vault.id;
  entity.amount = event.params.amount;
  entity.duration = event.params.duration;
  entity.blockNumber = event.block.number;
  entity.blockTimestamp = event.block.timestamp;
  entity.transactionHash = event.transaction.hash;
  entity.save();
}
