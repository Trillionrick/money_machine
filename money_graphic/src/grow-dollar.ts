import {
  Approval as ApprovalEvent,
  Transfer as TransferEvent,
  GrowDollar
} from "../generated/GrowDollar/GrowDollar"
import {
  Approval,
  Transfer,
  Token,
  HolderBalance,
  DailySnapshot
} from "../generated/schema"
import { Address, BigInt, ethereum } from "@graphprotocol/graph-ts"

const ZERO_ADDRESS = Address.zero()
const ZERO_BI = BigInt.zero()
const ONE_BI = BigInt.fromI32(1)

function getOrCreateToken(event: ethereum.Event): Token {
  let token = Token.load(event.address)
  if (token == null) {
    token = new Token(event.address)
    let contract = GrowDollar.bind(event.address)

    let nameResult = contract.try_name()
    if (!nameResult.reverted) {
      token.name = nameResult.value
    }

    let symbolResult = contract.try_symbol()
    if (!symbolResult.reverted) {
      token.symbol = symbolResult.value
    }

    let decimalsResult = contract.try_decimals()
    if (!decimalsResult.reverted) {
      token.decimals = decimalsResult.value
    }

    let supplyResult = contract.try_totalSupply()
    token.totalSupply = supplyResult.reverted ? ZERO_BI : supplyResult.value
    token.holderCount = 0
    token.lastUpdatedBlock = event.block.number
    token.lastUpdatedTimestamp = event.block.timestamp
  }

  return token as Token
}

function balanceId(token: Address, holder: Address): string {
  return token.toHexString() + "-" + holder.toHexString()
}

function getOrCreateBalance(
  token: Token,
  holder: Address,
  block: ethereum.Block
): HolderBalance {
  let id = balanceId(token.id as Address, holder)
  let balance = HolderBalance.load(id)
  if (balance == null) {
    balance = new HolderBalance(id)
    balance.holder = holder
    balance.token = token.id
    balance.balance = ZERO_BI
    balance.firstSeenBlock = block.number
  }

  balance.lastUpdatedBlock = block.number
  balance.lastUpdatedTimestamp = block.timestamp
  return balance as HolderBalance
}

function updateDailySnapshot(
  token: Token,
  event: TransferEvent,
  amount: BigInt
): void {
  let day = event.block.timestamp.toI32() / 86400
  let id = token.id.toHexString() + "-" + day.toString()
  let snapshot = DailySnapshot.load(id)
  if (snapshot == null) {
    snapshot = new DailySnapshot(id)
    snapshot.token = token.id
    snapshot.date = day
    snapshot.transferCount = 0
    snapshot.volume = ZERO_BI
  }

  snapshot.transferCount = snapshot.transferCount + 1
  snapshot.volume = snapshot.volume.plus(amount)
  snapshot.holderCount = token.holderCount
  snapshot.totalSupply = token.totalSupply
  snapshot.blockNumber = event.block.number
  snapshot.blockTimestamp = event.block.timestamp
  snapshot.save()
}

export function handleApproval(event: ApprovalEvent): void {
  let entity = new Approval(
    event.transaction.hash.concatI32(event.logIndex.toI32())
  )
  entity.owner = event.params.owner
  entity.spender = event.params.spender
  entity.value = event.params.value

  entity.blockNumber = event.block.number
  entity.blockTimestamp = event.block.timestamp
  entity.transactionHash = event.transaction.hash

  entity.save()
}

export function handleTransfer(event: TransferEvent): void {
  let entity = new Transfer(
    event.transaction.hash.concatI32(event.logIndex.toI32())
  )
  entity.from = event.params.from
  entity.to = event.params.to
  entity.value = event.params.value

  entity.blockNumber = event.block.number
  entity.blockTimestamp = event.block.timestamp
  entity.transactionHash = event.transaction.hash

  entity.save()

  let token = getOrCreateToken(event)
  let amount = event.params.value
  let fromIsZero = event.params.from.equals(ZERO_ADDRESS)
  let toIsZero = event.params.to.equals(ZERO_ADDRESS)

  if (!fromIsZero) {
    let fromBalance = getOrCreateBalance(token, event.params.from, event.block)
    let wasPositive = fromBalance.balance.gt(ZERO_BI)
    fromBalance.balance = fromBalance.balance.minus(amount)
    fromBalance.save()

    if (wasPositive && fromBalance.balance.equals(ZERO_BI)) {
      token.holderCount = token.holderCount - 1
    }
  }

  if (!toIsZero) {
    let toBalance = getOrCreateBalance(token, event.params.to, event.block)
    let wasZero = toBalance.balance.equals(ZERO_BI)
    toBalance.balance = toBalance.balance.plus(amount)
    toBalance.save()

    if (wasZero && toBalance.balance.gt(ZERO_BI)) {
      token.holderCount = token.holderCount + 1
    }
  }

  if (fromIsZero && !toIsZero) {
    token.totalSupply = token.totalSupply.plus(amount)
  } else if (toIsZero && !fromIsZero) {
    token.totalSupply = token.totalSupply.minus(amount)
  }

  token.lastUpdatedBlock = event.block.number
  token.lastUpdatedTimestamp = event.block.timestamp
  token.save()

  updateDailySnapshot(token, event, amount)
}
