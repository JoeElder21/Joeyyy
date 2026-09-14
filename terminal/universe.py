"""The tiered universe: what gets researched, how often, with how much budget."""

from __future__ import annotations

from dataclasses import dataclass

TIER_OWNED, TIER_MANDATE, TIER_SCREENED, TIER_MENTIONS = "T1", "T2", "T3", "T4"
TIERS = (TIER_OWNED, TIER_MANDATE, TIER_SCREENED, TIER_MENTIONS)
TIER_NAMES = {
    TIER_OWNED: "owned in any tracked account",
    TIER_MANDATE: "mandate model or watchlist",
    TIER_SCREENED: "passed a quantitative screen this week",
    TIER_MENTIONS: "mentioned in a feed, not yet screened",
}
REFRESH = {
    TIER_OWNED: "every run: price, catalysts, risk flags; full scorecard weekly or on a trigger",
    TIER_MANDATE: "every run: price and catalysts; full scorecard weekly",
    TIER_SCREENED: "daily price; scorecard when promoted to T2",
    TIER_MENTIONS: "weekly screen only; no scorecard",
}
# Bounded parallelism: how many researcher slots each tier may use per run.
DEFAULT_SLOTS = {TIER_OWNED: 4, TIER_MANDATE: 3, TIER_SCREENED: 2, TIER_MENTIONS: 1}


@dataclass(frozen=True)
class TierAssignment:
    tiers: dict[str, str]
    counts: dict[str, int]

    def members(self, tier: str) -> list[str]:
        return sorted(asset for asset, t in self.tiers.items() if t == tier)


def assign(
    owned: set[str], mandate: set[str], screened: set[str], mentions: set[str]
) -> TierAssignment:
    """Highest tier wins; an owned asset is T1 even if it is also a mention."""
    tiers: dict[str, str] = {}
    for tier, members in (
        (TIER_MENTIONS, mentions),
        (TIER_SCREENED, screened),
        (TIER_MANDATE, mandate),
        (TIER_OWNED, owned),
    ):
        for asset in members:
            tiers[asset] = tier
    counts = {tier: sum(1 for t in tiers.values() if t == tier) for tier in TIERS}
    return TierAssignment(tiers, counts)


def research_budget(
    assignment: TierAssignment, slots: dict[str, int] | None = None
) -> dict[str, dict]:
    """Assets per slot for each tier, so a run knows its bounded fan-out."""
    slots = slots or DEFAULT_SLOTS
    plan: dict[str, dict] = {}
    for tier in TIERS:
        members = assignment.members(tier)
        n = max(1, slots.get(tier, 1))
        batches = [members[i::n] for i in range(n)] if members else []
        plan[tier] = {"assets": len(members), "slots": n, "batches": [b for b in batches if b]}
    return plan
