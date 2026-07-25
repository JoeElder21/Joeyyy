"""Normalize Schwab account payloads into portfolio analytics.

Schwab's position records are wide and inconsistently populated across
account types, so every read here is defensive. A field that is absent
becomes ``None`` and is reported as unknown rather than as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

#: Instruments that represent cash sweep or money-market balances rather
#: than a tradable position with a thesis.
CASH_ASSET_TYPES = {"CASH_EQUIVALENT", "CURRENCY"}


def _number(source: dict[str, Any], *names: str) -> float | None:
    """Return the first present numeric field among ``names``."""
    for name in names:
        value = source.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def mask_account(account_number: str) -> str:
    """Show only the last four digits so a brief can be shared safely."""
    digits = "".join(ch for ch in str(account_number) if ch.isalnum())
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


@dataclass
class Holding:
    """One position, with cost basis and profit-and-loss resolved."""

    symbol: str
    description: str
    asset_type: str
    quantity: float
    average_price: float | None
    market_value: float
    day_pl: float | None = None
    unrealized_pl: float | None = None
    weight: float = 0.0

    @property
    def is_cash_like(self) -> bool:
        return self.asset_type in CASH_ASSET_TYPES

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def cost_basis(self) -> float | None:
        if self.average_price is None:
            return None
        return self.average_price * self.quantity

    @property
    def last_price(self) -> float | None:
        if not self.quantity:
            return None
        return self.market_value / self.quantity

    @property
    def unrealized_pl_pct(self) -> float | None:
        """Return on cost, as a decimal fraction."""
        basis = self.cost_basis
        if basis is None or basis == 0 or self.unrealized_pl is None:
            return None
        return self.unrealized_pl / abs(basis)

    @property
    def day_pl_pct(self) -> float | None:
        if self.day_pl is None or not self.market_value:
            return None
        opening_value = self.market_value - self.day_pl
        if opening_value == 0:
            return None
        return self.day_pl / abs(opening_value)


@dataclass
class Portfolio:
    """A single brokerage account resolved into holdings and totals."""

    account_label: str
    account_hash: str
    account_type: str
    holdings: list[Holding] = field(default_factory=list)
    cash: float = 0.0
    liquidation_value: float = 0.0

    @property
    def equity_holdings(self) -> list[Holding]:
        return [h for h in self.holdings if not h.is_cash_like]

    @property
    def invested_value(self) -> float:
        return sum(h.market_value for h in self.equity_holdings)

    @property
    def total_cost_basis(self) -> float | None:
        bases = [h.cost_basis for h in self.equity_holdings]
        if not bases or any(basis is None for basis in bases):
            return None
        return sum(basis for basis in bases if basis is not None)

    @property
    def unrealized_pl(self) -> float | None:
        values = [h.unrealized_pl for h in self.equity_holdings]
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    @property
    def unrealized_pl_pct(self) -> float | None:
        basis = self.total_cost_basis
        total = self.unrealized_pl
        if not basis or total is None:
            return None
        return total / abs(basis)

    @property
    def day_pl(self) -> float | None:
        values = [h.day_pl for h in self.equity_holdings if h.day_pl is not None]
        return sum(values) if values else None

    @property
    def cash_weight(self) -> float | None:
        if not self.liquidation_value:
            return None
        return self.cash / self.liquidation_value

    @property
    def largest_weight(self) -> float:
        return max((h.weight for h in self.equity_holdings), default=0.0)

    @property
    def concentration_index(self) -> float:
        """Herfindahl index of position weights.

        1.0 is a single position; 1/N is a perfectly even book. It is the
        cheapest single number for "is this portfolio actually diversified".
        """
        return sum(h.weight**2 for h in self.equity_holdings)

    @property
    def effective_positions(self) -> float:
        """Inverse Herfindahl: how many equal-weight positions this behaves like."""
        index = self.concentration_index
        return 1.0 / index if index else 0.0

    def symbols(self) -> list[str]:
        return [h.symbol for h in self.equity_holdings]

    def find(self, symbol: str) -> Holding | None:
        wanted = symbol.upper()
        return next((h for h in self.holdings if h.symbol.upper() == wanted), None)


def parse_position(raw: dict[str, Any]) -> Holding | None:
    """Convert one Schwab position record into a :class:`Holding`."""
    instrument = raw.get("instrument") or {}
    symbol = str(instrument.get("symbol") or "").strip()
    if not symbol:
        return None

    long_quantity = _number(raw, "longQuantity") or 0.0
    short_quantity = _number(raw, "shortQuantity") or 0.0
    quantity = long_quantity - short_quantity
    if quantity == 0:
        return None

    market_value = _number(raw, "marketValue") or 0.0
    average_price = _number(raw, "averagePrice", "averageLongPrice", "averageShortPrice")

    unrealized = _number(
        raw, "longOpenProfitLoss", "shortOpenProfitLoss", "openProfitLoss"
    )
    if unrealized is None and average_price is not None:
        unrealized = market_value - (average_price * quantity)

    return Holding(
        symbol=symbol,
        description=str(instrument.get("description") or symbol),
        asset_type=str(instrument.get("assetType") or "UNKNOWN"),
        quantity=quantity,
        average_price=average_price,
        market_value=market_value,
        day_pl=_number(raw, "currentDayProfitLoss"),
        unrealized_pl=unrealized,
    )


def parse_account(raw: dict[str, Any], account_hash: str = "") -> Portfolio:
    """Convert one Schwab account payload into a :class:`Portfolio`."""
    account = raw.get("securitiesAccount") or raw
    balances = account.get("currentBalances") or {}

    holdings = [
        holding
        for holding in (parse_position(p) for p in account.get("positions") or [])
        if holding is not None
    ]

    cash = _number(balances, "cashBalance", "totalCash", "cashAvailableForTrading") or 0.0
    liquidation = _number(balances, "liquidationValue", "equity")
    if liquidation is None:
        liquidation = sum(h.market_value for h in holdings) + cash

    portfolio = Portfolio(
        account_label=mask_account(account.get("accountNumber") or ""),
        account_hash=account_hash or str(account.get("hashValue") or ""),
        account_type=str(account.get("type") or "UNKNOWN"),
        holdings=holdings,
        cash=cash,
        liquidation_value=liquidation,
    )

    # Weights are shares of invested capital, not of total equity, so that a
    # large cash balance does not make every position look small.
    invested = portfolio.invested_value
    if invested:
        for holding in portfolio.equity_holdings:
            holding.weight = holding.market_value / invested

    portfolio.holdings.sort(key=lambda h: h.market_value, reverse=True)
    return portfolio


def parse_accounts(payload: Sequence[dict[str, Any]]) -> list[Portfolio]:
    return [parse_account(entry) for entry in payload]
