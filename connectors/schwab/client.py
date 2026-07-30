"""Read-only REST client for the Schwab Trader and Market Data APIs.

Scope note: this client never places, replaces, or cancels an order. The
order and transaction readers exist so the analytics layer can reconcile
fills and realized gains against current holdings.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from connectors.schwab.config import (
    MARKETDATA_BASE_URL,
    TRADER_BASE_URL,
    SchwabSettings,
)
from connectors.schwab.oauth import Clock, TokenStore, ensure_fresh
from connectors.schwab.transport import (
    HttpResponse,
    Transport,
    send_with_retry,
    urllib_transport,
)

#: Schwab accepts a long comma-joined symbol list, but batching keeps the
#: URL well under proxy limits and makes throttling failures cheap to retry.
QUOTE_BATCH_SIZE = 100


class SchwabError(RuntimeError):
    """Raised when a Schwab endpoint returns a non-success status."""

    def __init__(self, status: int, url: str, detail: str) -> None:
        super().__init__(f"HTTP {status} from {url}: {detail}")
        self.status = status
        self.url = url
        self.detail = detail


def _iso_millis(moment: datetime) -> str:
    """Schwab's order filters want ISO-8601 with milliseconds and a Z suffix."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _chunk(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class SchwabClient:
    """Authenticated reader for accounts, positions, quotes, and price history."""

    def __init__(
        self,
        settings: SchwabSettings,
        store: TokenStore | None = None,
        transport: Transport | None = None,
        now: Clock = time.time,
    ) -> None:
        self.settings = settings
        self.store = store or TokenStore(settings.token_path)
        self.transport = transport or urllib_transport(settings.request_timeout)
        self.now = now

    # ---- plumbing -------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        bundle = ensure_fresh(self.settings, self.store, self.transport, self.now)
        query = ""
        if params:
            cleaned = {k: v for k, v in params.items() if v is not None}
            if cleaned:
                query = "?" + urllib.parse.urlencode(cleaned)
        headers = {"Accept": "application/json", **bundle.authorization_header()}
        response: HttpResponse = send_with_retry(self.transport, "GET", url + query, headers)
        if not response.ok:
            raise SchwabError(response.status, url, response.text()[:500])
        return response.json()

    # ---- trader API -----------------------------------------------------

    def account_numbers(self) -> list[dict[str, str]]:
        """Map plain account numbers to the hashes every other call requires.

        Schwab does not accept a plain account number on any downstream
        endpoint, so this is always the first call of a session.
        """
        payload = self._get(f"{TRADER_BASE_URL}/accounts/accountNumbers")
        return list(payload or [])

    def accounts(self, with_positions: bool = True) -> list[dict[str, Any]]:
        """Return every linked brokerage account, optionally with positions."""
        payload = self._get(
            f"{TRADER_BASE_URL}/accounts",
            {"fields": "positions"} if with_positions else None,
        )
        return list(payload or [])

    def account(self, account_hash: str, with_positions: bool = True) -> dict[str, Any]:
        payload = self._get(
            f"{TRADER_BASE_URL}/accounts/{account_hash}",
            {"fields": "positions"} if with_positions else None,
        )
        return dict(payload or {})

    def orders(
        self,
        account_hash: str,
        lookback_days: int = 7,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read recent orders for reconciliation. This does not place orders."""
        end = datetime.now(UTC)
        payload = self._get(
            f"{TRADER_BASE_URL}/accounts/{account_hash}/orders",
            {
                "fromEnteredTime": _iso_millis(end - timedelta(days=lookback_days)),
                "toEnteredTime": _iso_millis(end),
                "status": status,
            },
        )
        return list(payload or [])

    def transactions(
        self,
        account_hash: str,
        lookback_days: int = 30,
        types: str = "TRADE",
    ) -> list[dict[str, Any]]:
        end = datetime.now(UTC)
        payload = self._get(
            f"{TRADER_BASE_URL}/accounts/{account_hash}/transactions",
            {
                "startDate": _iso_millis(end - timedelta(days=lookback_days)),
                "endDate": _iso_millis(end),
                "types": types,
            },
        )
        return list(payload or [])

    # ---- market data API ------------------------------------------------

    def quotes(self, symbols: Sequence[str], fields: str = "quote,fundamental") -> dict[str, Any]:
        """Fetch quotes for many symbols, batching to stay inside URL limits."""
        wanted = [s.strip().upper() for s in symbols if s and s.strip()]
        merged: dict[str, Any] = {}
        for batch in _chunk(wanted, QUOTE_BATCH_SIZE):
            payload = self._get(
                f"{MARKETDATA_BASE_URL}/quotes",
                {"symbols": ",".join(batch), "fields": fields, "indicative": "false"},
            )
            merged.update(payload or {})
        return merged

    def price_history(
        self,
        symbol: str,
        period_type: str = "year",
        period: int = 1,
        frequency_type: str = "daily",
        frequency: int = 1,
        need_extended_hours: bool = False,
    ) -> list[dict[str, Any]]:
        """Return daily candles, oldest first.

        One year of daily candles is the default because it is the shortest
        window that still supports a 200-day moving average and a 52-week
        range.
        """
        payload = self._get(
            f"{MARKETDATA_BASE_URL}/pricehistory",
            {
                "symbol": symbol.strip().upper(),
                "periodType": period_type,
                "period": period,
                "frequencyType": frequency_type,
                "frequency": frequency,
                "needExtendedHoursData": str(need_extended_hours).lower(),
            },
        )
        candles = list((payload or {}).get("candles") or [])
        candles.sort(key=lambda candle: candle.get("datetime", 0))
        return candles

    def market_hours(
        self, markets: Sequence[str] = ("equity",), on: date | None = None
    ) -> dict[str, Any]:
        """Report whether a market session is open, so a brief can say so."""
        payload = self._get(
            f"{MARKETDATA_BASE_URL}/markets",
            {
                "markets": ",".join(markets),
                "date": (on or date.today()).isoformat(),
            },
        )
        return dict(payload or {})

    def movers(self, index: str = "$SPX", sort: str = "PERCENT_CHANGE_UP") -> list[dict[str, Any]]:
        payload = self._get(
            f"{MARKETDATA_BASE_URL}/movers/{urllib.parse.quote(index)}",
            {"sort": sort},
        )
        return list((payload or {}).get("screeners") or [])

    # ---- convenience ----------------------------------------------------

    def load_history_map(
        self,
        symbols: Sequence[str],
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch one year of daily candles per symbol.

        A single bad symbol (a delisted ticker, a cash sweep pseudo-symbol)
        must not abort the whole brief, so failures are reported and skipped.
        """
        history: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            try:
                history[symbol] = self.price_history(symbol)
            except SchwabError as error:
                if on_error is not None:
                    on_error(symbol, error)
        return history
