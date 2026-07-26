"""Command line entry point for the Schwab connector.

    python -m connectors.schwab.cli login       # one browser consent, weekly
    python -m connectors.schwab.cli status      # token health and expiry
    python -m connectors.schwab.cli accounts    # linked accounts and hashes
    python -m connectors.schwab.cli positions   # current holdings
    python -m connectors.schwab.cli brief       # full analysed daily brief

``brief --json`` emits the same analysis as structured data, which is the
form the Market Operator agent consumes before its research pass.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from connectors.schwab.client import SchwabClient, SchwabError
from connectors.schwab.config import SchwabSettings, SettingsError
from connectors.schwab.oauth import (
    AuthError,
    TokenStore,
    build_authorize_url,
    exchange_code,
    verify_state,
)
from connectors.schwab.portfolio import Portfolio, parse_account
from connectors.schwab.report import render_brief
from connectors.schwab.signals import (
    Policy,
    PolicyError,
    evaluate_portfolio,
    portfolio_alerts,
)
from connectors.schwab.transport import urllib_transport


def _settings() -> SchwabSettings:
    return SchwabSettings.from_env()


def _client(settings: SchwabSettings) -> SchwabClient:
    return SchwabClient(
        settings,
        TokenStore(settings.token_path),
        urllib_transport(settings.request_timeout),
    )


def _select_portfolio(client: SchwabClient, account_suffix: str | None) -> Portfolio:
    """Resolve the account to analyse, preferring the largest by equity."""
    payload = client.accounts(with_positions=True)
    if not payload:
        raise SchwabError(200, "accounts", "Schwab returned no linked accounts.")
    portfolios = [parse_account(entry) for entry in payload]

    if account_suffix:
        wanted = account_suffix.strip()[-4:]
        matched = [p for p in portfolios if p.account_label.endswith(wanted)]
        if not matched:
            available = ", ".join(p.account_label for p in portfolios)
            raise SchwabError(
                404, "accounts", f"No account ending in {wanted}. Available: {available}"
            )
        return matched[0]

    portfolios.sort(key=lambda p: p.liquidation_value, reverse=True)
    return portfolios[0]


# ---- commands -----------------------------------------------------------


def cmd_login(args: argparse.Namespace) -> int:
    settings = _settings()
    url, state = build_authorize_url(settings)
    print("1. Open this URL in a browser and sign in to Schwab:\n")
    print(f"   {url}\n")
    print("2. Approve the accounts you want the agent to read.")
    print(
        "3. The browser will land on an error page — that is expected, the "
        "callback host is your own machine.\n"
        "   Copy the FULL address bar contents and paste it below.\n"
    )
    redirect = input("Pasted redirect URL: ").strip()

    try:
        verify_state(redirect, state)
    except AuthError as error:
        # A pasted bare code has no state to compare; only warn when a URL
        # was supplied and its state genuinely disagreed.
        if "code=" in redirect:
            print(f"error: {error}", file=sys.stderr)
            return 2

    bundle = exchange_code(settings, redirect, urllib_transport(settings.request_timeout))
    store = TokenStore(settings.token_path)
    store.save(bundle)
    days = bundle.refresh_seconds_left(time.time()) / 86400
    print(f"\nToken saved to {settings.token_path} (owner-only).")
    print(f"Re-consent required in {days:.1f} days. Set a calendar reminder.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = _settings()
    bundle = TokenStore(settings.token_path).load()
    if bundle is None:
        print(f"No token at {settings.token_path}. Run: login")
        return 1
    now = time.time()
    access_left = (bundle.access_expires_at - now) / 60
    refresh_left = bundle.refresh_seconds_left(now) / 86400
    print(f"Token store:      {settings.token_path}")
    print(
        f"Access valid:     {'yes' if bundle.access_valid(now) else 'no'} "
        f"({access_left:.0f} min remaining)"
    )
    print(
        f"Refresh valid:    {'yes' if bundle.refresh_valid(now) else 'no'} "
        f"({refresh_left:.1f} days remaining)"
    )
    print(f"Scope:            {bundle.scope or 'not reported'}")
    if refresh_left < 2:
        print("\nRe-consent is due. Run: python -m connectors.schwab.cli login")
    return 0 if bundle.refresh_valid(now) else 1


def cmd_accounts(args: argparse.Namespace) -> int:
    client = _client(_settings())
    for entry in client.account_numbers():
        number = str(entry.get("accountNumber", ""))
        print(f"****{number[-4:]}  hash={entry.get('hashValue', '')}")
    return 0


def cmd_positions(args: argparse.Namespace) -> int:
    settings = _settings()
    portfolio = _select_portfolio(_client(settings), args.account)
    print(
        f"{portfolio.account_label} ({portfolio.account_type})  "
        f"equity {portfolio.liquidation_value:,.2f}  cash {portfolio.cash:,.2f}\n"
    )
    header = (
        f"{'SYMBOL':<10}{'QTY':>10}{'AVG':>12}{'LAST':>12}{'VALUE':>14}{'WEIGHT':>9}{'P/L':>10}"
    )
    print(header)
    print("-" * len(header))
    for holding in portfolio.equity_holdings:
        pl = holding.unrealized_pl_pct
        print(
            f"{holding.symbol:<10}{holding.quantity:>10,.2f}"
            f"{(holding.average_price or 0):>12,.2f}"
            f"{(holding.last_price or 0):>12,.2f}"
            f"{holding.market_value:>14,.2f}"
            f"{holding.weight:>8.1%}"
            f"{(f'{pl:+.1%}' if pl is not None else '—'):>10}"
        )
    return 0


def _brief_payload(portfolio: Portfolio, verdicts: list, alerts: list[str]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "account": {
            "label": portfolio.account_label,
            "type": portfolio.account_type,
            "equity": portfolio.liquidation_value,
            "invested": portfolio.invested_value,
            "cash": portfolio.cash,
            "cash_weight": portfolio.cash_weight,
            "day_pl": portfolio.day_pl,
            "unrealized_pl": portfolio.unrealized_pl,
            "unrealized_pl_pct": portfolio.unrealized_pl_pct,
            "concentration_index": portfolio.concentration_index,
            "effective_positions": portfolio.effective_positions,
        },
        "portfolio_alerts": alerts,
        "positions": [
            {
                "symbol": v.symbol,
                "verdict": v.verdict,
                "score": v.score,
                "weight": v.weight,
                "market_value": v.market_value,
                "unrealized_pl_pct": v.unrealized_pl_pct,
                "metrics": asdict(v.metrics),
                "reasons": v.reasons,
                "guardrail_breaches": v.guardrail_breaches,
                "data_gaps": v.data_gaps,
                "research_questions": v.research_questions,
                "needs_corroboration": v.needs_corroboration,
            }
            for v in verdicts
        ],
    }


def cmd_brief(args: argparse.Namespace) -> int:
    settings = _settings()
    policy = Policy.load(settings.policy_path)
    client = _client(settings)
    portfolio = _select_portfolio(client, args.account)

    skipped: list[str] = []
    history = client.load_history_map(
        portfolio.symbols(),
        on_error=lambda symbol, error: skipped.append(f"{symbol}: {error}"),
    )
    verdicts = evaluate_portfolio(portfolio, history, policy)
    alerts = portfolio_alerts(portfolio, policy)
    for note in skipped:
        alerts.append(f"Price history unavailable — {note}")

    if args.json:
        output = json.dumps(_brief_payload(portfolio, verdicts, alerts), indent=2)
    else:
        output = render_brief(portfolio, verdicts, alerts)

    destination: Path | None = None
    if args.out:
        destination = Path(args.out)
    elif args.save:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        suffix = "json" if args.json else "md"
        destination = settings.report_dir / f"brief-{stamp}.{suffix}"

    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding="utf-8")
        print(f"Wrote {destination}", file=sys.stderr)

    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="connectors.schwab.cli",
        description="Read-only Schwab portfolio analysis. Places no orders.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="run the browser consent flow and store a token")
    sub.add_parser("status", help="report token validity and re-consent deadline")
    sub.add_parser("accounts", help="list linked accounts and their hashes")

    positions = sub.add_parser("positions", help="print current holdings")
    positions.add_argument("--account", help="last 4 digits of the account to read")

    brief = sub.add_parser("brief", help="produce the analysed daily brief")
    brief.add_argument("--account", help="last 4 digits of the account to read")
    brief.add_argument("--json", action="store_true", help="emit structured data")
    brief.add_argument("--save", action="store_true", help="also write to the report directory")
    brief.add_argument("--out", help="write the brief to this path")

    return parser


HANDLERS = {
    "login": cmd_login,
    "status": cmd_status,
    "accounts": cmd_accounts,
    "positions": cmd_positions,
    "brief": cmd_brief,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (SettingsError, PolicyError, AuthError, SchwabError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
