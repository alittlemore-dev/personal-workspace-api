from enum import StrEnum


class AssetSource(StrEnum):
    WEB = "web"
    PAT = "pat"


class AssetPositionKind(StrEnum):
    CASH = "cash"
    BANK = "bank"
    BROKER_CASH = "brokerCash"
    SAVINGS = "savings"
    DEPOSIT = "deposit"
    STOCK = "stock"
    BOND = "bond"
    FUND = "fund"
    OTHER = "other"

    @property
    def security(self) -> bool:
        return self in {self.STOCK, self.BOND, self.FUND}

    @property
    def monetary(self) -> bool:
        return not self.security and self != self.OTHER


class AssetMovementKind(StrEnum):
    OPENING_EXTERNAL = "openingExternal"
    OPENING_BUDGET = "openingBudget"
    STATEMENT = "statement"
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"
    DEPOSIT_EXTERNAL = "depositExternal"
    WITHDRAW_EXTERNAL = "withdrawExternal"
    TRANSFER = "transfer"
    EXCHANGE = "exchange"
    BUY = "buy"
    BUY_FROM_BUDGET = "buyFromBudget"
    SELL = "sell"
    PAYOUT = "payout"
    PAYOUT_TO_BUDGET = "payoutToBudget"
    FEE = "fee"
    VALUATION = "valuation"
    RECONCILE = "reconcile"

    @property
    def affects_budget(self) -> bool:
        return self in {
            self.OPENING_BUDGET,
            self.BUY_FROM_BUDGET,
            self.CONTRIBUTION,
            self.WITHDRAWAL,
            self.PAYOUT_TO_BUDGET,
        }

    @property
    def notifies(self) -> bool:
        return self in {
            self.DEPOSIT_EXTERNAL,
            self.WITHDRAW_EXTERNAL,
            self.CONTRIBUTION,
            self.BUY_FROM_BUDGET,
            self.WITHDRAWAL,
            self.PAYOUT,
            self.PAYOUT_TO_BUDGET,
        }
