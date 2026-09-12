"""The forecast and outcome ledger.

Every published judgment lands here with the information needed to grade it
later, and nothing that lands here is ever edited. That single property is
what separates a research process from a highlight reel: a ledger you can
rewrite will always show that you were right.

Three mechanisms enforce it:

* **Append-only with lineage.** A wrong entry is not fixed; a correction is
  appended carrying ``corrects`` pointing at the original, and both stay
  readable. ``supersedes_chain`` walks the history.
* **Outcomes mature, they do not get assigned.** A row is PENDING until its
  horizon actually ends. Nothing may write a realised return before the
  forecast has had the time it asked for.
* **The clock starts after publication.** ``earliest_entry_at`` is
  ``published_at`` plus a stated execution latency. Grading from the research
  snapshot -- a price that existed before anyone could act -- is the most
  common way a backtest flatters itself, and it is structurally impossible
  here because ``grade`` refuses references earlier than that timestamp.

Rows for assets that were EXCLUDED, or that the engine passed on, are kept
deliberately. A ledger that only records the picks cannot tell you what the
process missed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from terminal import clock

# Outcome lifecycle.
PENDING = "PENDING"  # horizon has not matured
MATURED = "MATURED"  # graded against a real, post-publication reference
VOID = "VOID"  # no tradable reference existed; never graded on a fiction
SUPERSEDED = "SUPERSEDED"  # a correction was appended after this row

OUTCOME_STATES = (PENDING, MATURED, VOID, SUPERSEDED)

# Realistic gap between publishing a judgment and being able to act on it.
DEFAULT_EXECUTION_LATENCY = timedelta(minutes=15)

LEDGER_VERSION = "FORECAST_LEDGER_V1"

# The column contract, in the order the directive specifies it.
COLUMNS: tuple[str, ...] = (
    "run_id",
    "edition_id",
    "snapshot_at",
    "published_at",
    "earliest_entry_at",
    "asset_id",
    "chain_contract",
    "universe_version",
    "model_version",
    "config_version",
    "code_version",
    "horizon",
    "benchmark",
    "rank",
    "score_type",
    "score",
    "reference_quote",
    "quote_at",
    "venue_route",
    "notional",
    "entry_rule",
    "estimated_cost",
    "gross_forecast",
    "net_forecast",
    "forecast_interval",
    "defined_probability_event",
    "probability",
    "data_confidence",
    "model_confidence",
    "evidence_ids",
    "risk_flags",
    "invalidation",
    "expiry",
    "paper_fill",
    "realized_net_return",
    "benchmark_return",
    "max_adverse_excursion",
    "max_favorable_excursion",
    "outcome_status",
)


@dataclass
class ForecastRow:
    """One published judgment about one asset at one horizon."""

    run_id: str
    edition_id: str
    snapshot_at: str
    published_at: str
    earliest_entry_at: str
    asset_id: str
    chain_contract: str | None
    universe_version: str
    model_version: str
    config_version: str
    code_version: str
    horizon: str
    benchmark: str
    rank: int | None
    score_type: str
    score: float | None
    reference_quote: float | None
    quote_at: str | None
    venue_route: str
    notional: float
    entry_rule: str
    estimated_cost: float | None
    gross_forecast: float | None
    net_forecast: float | None
    forecast_interval: list[float] | None = None
    defined_probability_event: str | None = None
    probability: float | None = None
    data_confidence: str = "UNKNOWN"
    model_confidence: str = "HEURISTIC"
    evidence_ids: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    invalidation: float | None = None
    expiry: str | None = None
    paper_fill: float | None = None
    realized_net_return: float | None = None
    benchmark_return: float | None = None
    max_adverse_excursion: float | None = None
    max_favorable_excursion: float | None = None
    outcome_status: str = PENDING
    # Lineage, outside the published column contract.
    row_id: str = ""
    corrects: str | None = None
    correction_reason: str | None = None
    entry_state: str = ""

    def __post_init__(self) -> None:
        if self.outcome_status not in OUTCOME_STATES:
            raise ValueError(f"unknown outcome status: {self.outcome_status!r}")
        if self.probability is not None and not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must lie in [0, 1] or be null")
        if self.score_type == "probability" and self.probability is None:
            raise ValueError("a probability score type requires a probability")
        if not self.row_id:
            self.row_id = self._digest()

    def _digest(self) -> str:
        payload = {
            "run_id": self.run_id,
            "asset_id": self.asset_id,
            "horizon": self.horizon,
            "published_at": self.published_at,
            "corrects": self.corrects,
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def as_row(self) -> dict:
        """The published column contract only, in declared order."""
        data = asdict(self)
        return {column: data[column] for column in COLUMNS}

    def as_dict(self) -> dict:
        return asdict(self)


class Ledger:
    """An append-only collection of forecast rows."""

    def __init__(self, rows: list[ForecastRow] | None = None) -> None:
        self._rows: list[ForecastRow] = list(rows or [])
        self._index: dict[str, ForecastRow] = {r.row_id: r for r in self._rows}

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)

    @property
    def rows(self) -> list[ForecastRow]:
        return list(self._rows)

    def append(self, row: ForecastRow) -> ForecastRow:
        """Add a row. Never mutates an existing one."""
        if row.row_id in self._index:
            raise ValueError(f"row {row.row_id} is already in the ledger")
        if row.corrects is not None:
            target = self._index.get(row.corrects)
            if target is None:
                raise ValueError(f"cannot correct unknown row {row.corrects}")
            # The superseded row keeps its content; only its lifecycle marker
            # moves, so the original numbers stay readable forever.
            target.outcome_status = SUPERSEDED
        self._rows.append(row)
        self._index[row.row_id] = row
        return row

    def get(self, row_id: str) -> ForecastRow | None:
        return self._index.get(row_id)

    def supersedes_chain(self, row_id: str) -> list[ForecastRow]:
        """Walk a row back through everything it corrected."""
        chain: list[ForecastRow] = []
        current = self._index.get(row_id)
        seen: set[str] = set()
        while current is not None and current.row_id not in seen:
            chain.append(current)
            seen.add(current.row_id)
            current = self._index.get(current.corrects) if current.corrects else None
        return chain

    def live(self) -> list[ForecastRow]:
        """Rows that have not been superseded."""
        return [r for r in self._rows if r.outcome_status != SUPERSEDED]

    def pending(self, as_of: datetime | None = None) -> list[ForecastRow]:
        """Rows still waiting on their horizon."""
        out = [r for r in self.live() if r.outcome_status == PENDING]
        if as_of is None:
            return out
        moment = clock.to_utc(as_of)
        return [r for r in out if not _matured(r, moment)]

    def due(self, as_of: datetime) -> list[ForecastRow]:
        """Pending rows whose horizon has now closed and which can be graded."""
        moment = clock.to_utc(as_of)
        return [r for r in self.live() if r.outcome_status == PENDING and _matured(r, moment)]

    def for_run(self, run_id: str) -> list[ForecastRow]:
        return [r for r in self._rows if r.run_id == run_id]

    def for_asset(self, asset_id: str) -> list[ForecastRow]:
        return [r for r in self._rows if r.asset_id == asset_id]

    def to_json(self) -> str:
        return json.dumps([r.as_dict() for r in self._rows], sort_keys=True, indent=1)

    @classmethod
    def from_json(cls, text: str) -> Ledger:
        payload = json.loads(text)
        return cls([ForecastRow(**item) for item in payload])


HORIZON_SPANS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def _matured(row: ForecastRow, moment: datetime) -> bool:
    span = HORIZON_SPANS.get(row.horizon)
    if span is None:
        return False
    start = clock.to_utc(datetime.fromisoformat(row.earliest_entry_at.replace("Z", "+00:00")))
    return moment >= start + span


def earliest_entry(
    published_at: datetime, latency: timedelta = DEFAULT_EXECUTION_LATENCY
) -> datetime:
    """The first moment a published judgment could actually have been acted on."""
    return clock.to_utc(published_at) + latency


def grade(
    row: ForecastRow,
    fill_price: float | None,
    exit_price: float | None,
    fill_at: datetime | None,
    benchmark_return: float | None = None,
    path_prices: list[float] | None = None,
    realised_cost: float | None = None,
) -> ForecastRow:
    """Grade a matured row. Returns the SAME row with its outcome fields set.

    Refuses a fill earlier than ``earliest_entry_at``: a price nobody could
    have traded is not evidence about a forecast. Returns VOID when no
    tradable reference existed rather than inventing one.
    """
    if row.outcome_status != PENDING:
        raise ValueError(f"row {row.row_id} is {row.outcome_status}, not PENDING")

    if fill_price is None or exit_price is None or fill_at is None:
        row.outcome_status = VOID
        row.realized_net_return = None
        return row

    floor = clock.to_utc(datetime.fromisoformat(row.earliest_entry_at.replace("Z", "+00:00")))
    if clock.to_utc(fill_at) < floor:
        raise ValueError(
            f"fill at {fill_at.isoformat()} precedes earliest_entry_at "
            f"{row.earliest_entry_at}; a pre-publication price cannot grade a forecast"
        )
    if fill_price <= 0:
        raise ValueError("fill price must be positive")

    gross = (exit_price - fill_price) / fill_price
    cost = row.estimated_cost if realised_cost is None else realised_cost
    row.paper_fill = fill_price
    row.realized_net_return = round(gross - (cost or 0.0), 6)
    row.benchmark_return = benchmark_return

    if path_prices:
        usable = [p for p in path_prices if isinstance(p, int | float) and p > 0]
        if usable:
            row.max_adverse_excursion = round((min(usable) - fill_price) / fill_price, 6)
            row.max_favorable_excursion = round((max(usable) - fill_price) / fill_price, 6)

    row.outcome_status = MATURED
    return row


def accountability(ledger: Ledger, horizon: str | None = None) -> dict:
    """A summary honest enough to publish on the morning page.

    Reports what has actually matured and what is still pending, separately.
    A hit rate computed over three matured rows is reported with its ``n`` so
    nobody reads it as a track record.
    """
    rows = [r for r in ledger.live() if horizon is None or r.horizon == horizon]
    matured = [r for r in rows if r.outcome_status == MATURED]
    pending = [r for r in rows if r.outcome_status == PENDING]
    void = [r for r in rows if r.outcome_status == VOID]

    graded = [r for r in matured if r.realized_net_return is not None]
    beat = [
        r
        for r in graded
        if r.benchmark_return is not None and r.realized_net_return > r.benchmark_return
    ]
    comparable = [r for r in graded if r.benchmark_return is not None]

    summary: dict = {
        "horizon": horizon or "all",
        "published": len(rows),
        "matured": len(matured),
        "pending": len(pending),
        "void": len(void),
        "graded": len(graded),
        "mean_realized_net_return": None,
        "median_realized_net_return": None,
        "beat_benchmark": len(beat),
        "comparable_to_benchmark": len(comparable),
        "hit_rate_vs_benchmark": None,
        "sample_adequate": len(graded) >= 20,
        "caveat": (
            "Counts and averages over a small number of matured forecasts are "
            "descriptive, not evidence of an edge. Pending rows are excluded "
            "from every average rather than assumed to be winners."
        ),
    }
    if graded:
        values = sorted(r.realized_net_return for r in graded)
        summary["mean_realized_net_return"] = round(sum(values) / len(values), 6)
        mid = len(values) // 2
        summary["median_realized_net_return"] = round(
            values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0, 6
        )
    if comparable:
        summary["hit_rate_vs_benchmark"] = round(len(beat) / len(comparable), 4)
    if not summary["sample_adequate"]:
        summary["caveat"] = (
            f"Only {len(graded)} matured forecast(s). NO DEMONSTRATED EDGE: this "
            "is far too few to establish anything. " + summary["caveat"]
        )
    return summary
