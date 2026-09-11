"""Claude Stocks Terminal: the research-workflow package.

Deterministic, stdlib-only building blocks for the daily research run: document
schemas, asset identity, the market clock, field-level freshness, the 100-point
equity scorecard, scenario mathematics, outcome grading, fatal-risk and release
gates, the tiered universe, run manifests with a hash chain and idempotency keys,
the two-round critic protocol, and the store adapters.

Nothing in this package places an order, talks to a broker, or holds a
credential. It produces research documents and a rendered page; a human decides.
"""

__version__ = "0.1.0"
