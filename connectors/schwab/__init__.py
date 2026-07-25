"""Charles Schwab Trader API connector.

Read-only by design. This package authenticates against the Schwab
Individual Developer Platform, reads accounts, positions, quotes, and price
history, and turns them into portfolio analytics and a rules-based daily
brief.

Nothing in this package places, modifies, or cancels an order. The order
endpoints are read-only helpers used to reconcile fills against holdings.

No module here performs network I/O at import time, and no credential is
ever written to the repository.
"""

from __future__ import annotations

__all__ = [
    "SchwabSettings",
    "SchwabClient",
    "SchwabError",
    "TokenBundle",
    "TokenStore",
]

from connectors.schwab.config import SchwabSettings
from connectors.schwab.oauth import TokenBundle, TokenStore
from connectors.schwab.client import SchwabClient, SchwabError
