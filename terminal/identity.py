"""Asset identity: contract-first for crypto, exchange-qualified for equities.

Two assets that print the same symbol are different assets. The live terminal
learned this the hard way (a symbol search returning a different pool than the
one a row described), so every document in the store keys an asset by its
canonical id, never by its symbol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
BASE58_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
TICKER = re.compile(r"^[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z]{1,2})?$")
MIC = re.compile(r"^X[A-Z]{3}$")
OCC_OPTION = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")
CHAIN = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

EVM_CHAINS = frozenset(
    {
        "ethereum",
        "pulsechain",
        "bsc",
        "base",
        "arbitrum",
        "polygon",
        "avalanche",
        "optimism",
        "peaq",
    }
)
BASE58_CHAINS = frozenset({"solana"})
NATIVE_KEY = "native"
ASSET_CLASSES = ("equity", "crypto", "option", "cash")
_PREFIX = {"equity": "eq", "crypto": "cx", "option": "op", "cash": "cash"}
_CLASS_BY_PREFIX = {value: key for key, value in _PREFIX.items()}


@dataclass(frozen=True)
class AssetId:
    """One asset, identified by class, venue and a venue-specific key."""

    asset_class: str
    symbol: str
    venue: str
    key: str

    @property
    def canonical(self) -> str:
        return f"{_PREFIX[self.asset_class]}:{self.venue}:{self.key}"

    def __str__(self) -> str:
        return self.canonical


def normalize_contract(chain: str, contract: str) -> str:
    """Lower-case EVM addresses; keep base58 case (it is significant)."""
    contract = contract.strip()
    if chain in EVM_CHAINS:
        return contract.lower()
    return contract


def equity(ticker: str, exchange: str) -> AssetId:
    return AssetId("equity", ticker.upper(), exchange.upper(), ticker.upper())


def crypto(symbol: str, chain: str, contract: str | None = None) -> AssetId:
    chain = chain.lower()
    key = NATIVE_KEY if contract is None else normalize_contract(chain, contract)
    return AssetId("crypto", symbol, chain, key)


def option(underlying: str, exchange: str, occ_symbol: str) -> AssetId:
    return AssetId("option", underlying.upper(), exchange.upper(), occ_symbol.upper())


def cash(currency: str = "USD", account: str = "any") -> AssetId:
    return AssetId("cash", currency.upper(), account, currency.upper())


def parse(text: str, symbol: str | None = None) -> AssetId:
    """Parse a canonical id such as ``eq:XNAS:NVDA`` or ``cx:pulsechain:0x...``."""
    parts = text.split(":", 2)
    if len(parts) != 3 or parts[0] not in _CLASS_BY_PREFIX:
        raise ValueError(f"not a canonical asset id: {text!r}")
    asset_class = _CLASS_BY_PREFIX[parts[0]]
    venue, key = parts[1], parts[2]
    if asset_class == "crypto":
        key = NATIVE_KEY if key == NATIVE_KEY else normalize_contract(venue, key)
    return AssetId(asset_class, symbol or (key if asset_class != "crypto" else ""), venue, key)


def validate(asset: AssetId) -> list[str]:
    """Return the identity problems, empty when the id is well formed."""
    problems: list[str] = []
    if asset.asset_class not in ASSET_CLASSES:
        return [f"unknown asset class {asset.asset_class!r}"]
    if asset.asset_class == "equity":
        if not TICKER.match(asset.key):
            problems.append(f"ticker {asset.key!r} is not a valid symbol")
        if not MIC.match(asset.venue):
            problems.append(f"exchange {asset.venue!r} is not an ISO 10383 MIC")
    elif asset.asset_class == "crypto":
        if not CHAIN.match(asset.venue):
            problems.append(f"chain {asset.venue!r} is not a chain slug")
        if not asset.symbol:
            problems.append("crypto assets need a display symbol")
        if asset.key == NATIVE_KEY:
            pass
        elif asset.venue in EVM_CHAINS:
            if not EVM_ADDRESS.match(asset.key):
                problems.append(f"{asset.key!r} is not an EVM contract address")
            elif asset.key != asset.key.lower():
                problems.append("EVM contract addresses are stored lower-case")
        elif asset.venue in BASE58_CHAINS:
            if not BASE58_ADDRESS.match(asset.key):
                problems.append(f"{asset.key!r} is not a base58 mint address")
        elif not asset.key:
            problems.append("contract address is required for a non-native token")
    elif asset.asset_class == "option":
        if not OCC_OPTION.match(asset.key):
            problems.append(f"{asset.key!r} is not an OCC option symbol")
    return problems


def collisions(assets: list[AssetId]) -> dict[str, list[str]]:
    """Symbols that map to more than one canonical id: the lookalike trap."""
    by_symbol: dict[str, set[str]] = {}
    for asset in assets:
        by_symbol.setdefault(asset.symbol.upper(), set()).add(asset.canonical)
    return {symbol: sorted(ids) for symbol, ids in by_symbol.items() if len(ids) > 1}
