"""Offline tests for the Schwab connector.

Every network call is served by an injected fake transport. Nothing in this
module contacts Schwab, and no real credential is required to run it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.schwab import indicators, report, signals  # noqa: E402
from connectors.schwab.client import SchwabClient, SchwabError  # noqa: E402
from connectors.schwab.config import (  # noqa: E402
    REFRESH_TTL_SECONDS,
    SchwabSettings,
    SettingsError,
)
from connectors.schwab.oauth import (  # noqa: E402
    AuthError,
    ReconsentRequired,
    TokenBundle,
    TokenStore,
    build_authorize_url,
    ensure_fresh,
    exchange_code,
    extract_code,
    renew,
    verify_state,
)
from connectors.schwab.portfolio import (  # noqa: E402
    mask_account,
    parse_account,
    parse_position,
)
from connectors.schwab.transport import HttpResponse, send_with_retry  # noqa: E402

POLICY_PATH = ROOT / "config" / "portfolio_policy.toml"
NOW = 1_700_000_000.0


class FakeTransport:
    """Serves canned responses and records every request made."""

    def __init__(self, responses: list[HttpResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[tuple[str, str, dict, bytes | None]] = []
        self.default = HttpResponse(200, b"{}")

    def __call__(self, method, url, headers, body):
        self.requests.append((method, url, dict(headers), body))
        if self.responses:
            return self.responses.pop(0)
        return self.default

    @property
    def last_url(self) -> str:
        return self.requests[-1][1]

    def urls(self) -> list[str]:
        return [request[1] for request in self.requests]


def json_response(payload, status: int = 200) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"))


def settings_for(tmp: Path) -> SchwabSettings:
    return SchwabSettings(
        app_key="key-abc",
        app_secret="shh-123",
        callback_url="https://127.0.0.1:8182",
        token_path=tmp / "token.json",
        policy_path=POLICY_PATH,
        report_dir=tmp / "reports",
    )


def token_payload(access: str = "acc-1", refresh: str = "ref-1", expires_in: int = 1800):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "api",
    }


def fresh_bundle(now: float = NOW) -> TokenBundle:
    return TokenBundle(
        access="acc-1",
        refresh="ref-1",
        access_expires_at=now + 1800,
        refresh_expires_at=now + REFRESH_TTL_SECONDS,
    )


def candles(closes, volume: float = 1_000.0):
    """Build daily candles from a close series with a plausible bar shape."""
    built = []
    for index, close in enumerate(closes):
        built.append(
            {
                "datetime": 1_600_000_000_000 + index * 86_400_000,
                "open": close * 0.995,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": float(close),
                "volume": volume,
            }
        )
    return built


def rising_series(length: int = 300, start: float = 50.0, step: float = 0.25):
    return [start + step * i for i in range(length)]


def falling_series(length: int = 300, start: float = 150.0, step: float = 0.3):
    return [max(1.0, start - step * i) for i in range(length)]


# ---------------------------------------------------------------- settings


class SettingsTests(unittest.TestCase):
    def test_missing_credentials_are_reported_by_name(self):
        with self.assertRaises(SettingsError) as caught:
            SchwabSettings.from_env(env={}, dotenv_path=Path("/nonexistent/.env"))
        message = str(caught.exception)
        self.assertIn("SCHWAB_APP_KEY", message)
        self.assertIn("SCHWAB_APP_SECRET", message)

    def test_environment_values_are_used(self):
        resolved = SchwabSettings.from_env(
            env={"SCHWAB_APP_KEY": "k", "SCHWAB_APP_SECRET": "s"},
            dotenv_path=Path("/nonexistent/.env"),
        )
        self.assertEqual(resolved.app_key, "k")
        self.assertEqual(resolved.callback_url, "https://127.0.0.1:8182")

    def test_dotenv_is_layered_under_the_environment(self):
        with tempfile.TemporaryDirectory() as raw:
            dotenv = Path(raw) / "env"
            dotenv.write_text(
                '# comment\nSCHWAB_APP_KEY="from-file"\nSCHWAB_APP_SECRET=file-secret\n',
                encoding="utf-8",
            )
            resolved = SchwabSettings.from_env(
                env={"SCHWAB_APP_KEY": "from-env"}, dotenv_path=dotenv
            )
        self.assertEqual(resolved.app_key, "from-env")
        self.assertEqual(resolved.app_secret, "file-secret")


# ------------------------------------------------------------------- oauth


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = settings_for(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_authorize_url_carries_client_and_callback(self):
        url, state = build_authorize_url(self.settings)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["client_id"], ["key-abc"])
        self.assertEqual(query["redirect_uri"], ["https://127.0.0.1:8182"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["state"], [state])

    def test_code_survives_percent_encoding(self):
        # Schwab appends an encoded '@' that naive string splitting corrupts.
        raw = "https://127.0.0.1:8182/?code=abc123%40&session=xyz"
        self.assertEqual(extract_code(raw), "abc123@")

    def test_bare_code_passes_through(self):
        self.assertEqual(extract_code("  plaincode  "), "plaincode")

    def test_empty_redirect_is_rejected(self):
        with self.assertRaises(AuthError):
            extract_code("   ")

    def test_state_mismatch_is_rejected(self):
        with self.assertRaises(AuthError):
            verify_state("https://127.0.0.1:8182/?code=a&state=wrong", "right")

    def test_state_match_is_accepted(self):
        verify_state("https://127.0.0.1:8182/?code=a&state=right", "right")

    def test_exchange_posts_authorization_code_grant(self):
        transport = FakeTransport([json_response(token_payload())])
        bundle = exchange_code(self.settings, "?code=xyz", transport, now=lambda: NOW)

        method, url, headers, body = transport.requests[0]
        form = urllib.parse.parse_qs(body.decode("utf-8"))
        self.assertEqual(method, "POST")
        self.assertIn("/v1/oauth/token", url)
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(form["grant_type"], ["authorization_code"])
        self.assertEqual(form["code"], ["xyz"])
        self.assertEqual(form["redirect_uri"], ["https://127.0.0.1:8182"])
        self.assertEqual(bundle.access, "acc-1")
        self.assertAlmostEqual(bundle.access_expires_at, NOW + 1800)
        self.assertAlmostEqual(bundle.refresh_expires_at, NOW + REFRESH_TTL_SECONDS)

    def test_failed_exchange_explains_the_likely_cause(self):
        transport = FakeTransport([HttpResponse(400, b"bad")])
        with self.assertRaises(AuthError) as caught:
            exchange_code(self.settings, "?code=xyz", transport, now=lambda: NOW)
        self.assertIn("callback URL", str(caught.exception))

    def test_renewal_keeps_the_original_seven_day_deadline(self):
        # Schwab does not extend the refresh window on renewal; if the code
        # ever "resets" it, the agent would silently miss its re-consent.
        original = fresh_bundle()
        later = NOW + 3600
        transport = FakeTransport([json_response(token_payload(access="acc-2"))])

        renewed = renew(self.settings, original, transport, now=lambda: later)

        form = urllib.parse.parse_qs(transport.requests[0][3].decode("utf-8"))
        self.assertEqual(form["grant_type"], ["refresh_token"])
        self.assertEqual(renewed.access, "acc-2")
        self.assertAlmostEqual(renewed.access_expires_at, later + 1800)
        self.assertAlmostEqual(renewed.refresh_expires_at, original.refresh_expires_at)

    def test_renewal_after_seven_days_demands_reconsent(self):
        expired = fresh_bundle()
        with self.assertRaises(ReconsentRequired):
            renew(
                self.settings,
                expired,
                FakeTransport(),
                now=lambda: NOW + REFRESH_TTL_SECONDS + 1,
            )

    def test_rejected_refresh_credential_demands_reconsent(self):
        transport = FakeTransport([HttpResponse(401, b"nope")])
        with self.assertRaises(ReconsentRequired):
            renew(self.settings, fresh_bundle(), transport, now=lambda: NOW + 60)

    def test_token_store_round_trip_is_owner_only(self):
        store = TokenStore(self.settings.token_path)
        self.assertIsNone(store.load())

        store.save(fresh_bundle())
        loaded = store.load()
        self.assertEqual(loaded.access, "acc-1")
        self.assertEqual(loaded.refresh, "ref-1")

        mode = stat.S_IMODE(self.settings.token_path.stat().st_mode)
        self.assertEqual(mode, 0o600)

        store.clear()
        self.assertIsNone(store.load())

    def test_corrupt_token_store_raises_rather_than_returning_none(self):
        self.settings.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.token_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(AuthError):
            TokenStore(self.settings.token_path).load()

    def test_ensure_fresh_reuses_a_valid_access_credential(self):
        store = TokenStore(self.settings.token_path)
        store.save(fresh_bundle())
        transport = FakeTransport()

        bundle = ensure_fresh(self.settings, store, transport, now=lambda: NOW + 60)

        self.assertEqual(bundle.access, "acc-1")
        self.assertEqual(transport.requests, [])

    def test_ensure_fresh_renews_and_persists_when_expired(self):
        store = TokenStore(self.settings.token_path)
        store.save(fresh_bundle())
        transport = FakeTransport([json_response(token_payload(access="acc-9"))])

        bundle = ensure_fresh(self.settings, store, transport, now=lambda: NOW + 2000)

        self.assertEqual(bundle.access, "acc-9")
        self.assertEqual(store.load().access, "acc-9")

    def test_missing_token_store_demands_login(self):
        with self.assertRaises(ReconsentRequired):
            ensure_fresh(
                self.settings,
                TokenStore(self.settings.token_path),
                FakeTransport(),
                now=lambda: NOW,
            )


# --------------------------------------------------------------- transport


class TransportTests(unittest.TestCase):
    def test_throttled_request_is_retried_then_succeeds(self):
        transport = FakeTransport(
            [HttpResponse(429, b""), HttpResponse(429, b""), json_response({"ok": True})]
        )
        naps: list[float] = []

        response = send_with_retry(
            transport, "GET", "https://example.test", {}, sleep=naps.append
        )

        self.assertTrue(response.ok)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(naps, [1.0, 2.0])

    def test_client_error_is_not_retried(self):
        transport = FakeTransport([HttpResponse(404, b"")])
        response = send_with_retry(
            transport, "GET", "https://example.test", {}, sleep=lambda _: None
        )
        self.assertEqual(response.status, 404)
        self.assertEqual(len(transport.requests), 1)


# ------------------------------------------------------------------ client


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = settings_for(Path(self.tmp.name))
        self.store = TokenStore(self.settings.token_path)
        self.store.save(fresh_bundle())

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, responses) -> tuple[SchwabClient, FakeTransport]:
        transport = FakeTransport(responses)
        return (
            SchwabClient(self.settings, self.store, transport, now=lambda: NOW + 60),
            transport,
        )

    def test_account_numbers_hits_the_hash_endpoint(self):
        client, transport = self.client(
            [json_response([{"accountNumber": "12345678", "hashValue": "HASH"}])]
        )
        result = client.account_numbers()
        self.assertIn("/trader/v1/accounts/accountNumbers", transport.last_url)
        self.assertEqual(result[0]["hashValue"], "HASH")

    def test_accounts_requests_positions_and_sends_the_bearer_credential(self):
        client, transport = self.client([json_response([])])
        client.accounts()
        self.assertIn("fields=positions", transport.last_url)
        self.assertEqual(transport.requests[0][2]["Authorization"], "Bearer acc-1")

    def test_price_history_is_sorted_oldest_first(self):
        payload = {
            "candles": [
                {"datetime": 3, "close": 3},
                {"datetime": 1, "close": 1},
                {"datetime": 2, "close": 2},
            ]
        }
        client, transport = self.client([json_response(payload)])
        result = client.price_history("aapl")
        self.assertEqual([c["datetime"] for c in result], [1, 2, 3])
        self.assertIn("symbol=AAPL", transport.last_url)
        self.assertIn("periodType=year", transport.last_url)

    def test_quotes_are_batched_and_merged(self):
        symbols = [f"SYM{i}" for i in range(150)]
        client, transport = self.client(
            [json_response({"SYM0": {}}), json_response({"SYM100": {}})]
        )
        merged = client.quotes(symbols)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(set(merged), {"SYM0", "SYM100"})

    def test_error_status_becomes_a_typed_exception(self):
        client, _ = self.client([HttpResponse(403, b"forbidden")])
        with self.assertRaises(SchwabError) as caught:
            client.accounts()
        self.assertEqual(caught.exception.status, 403)

    def test_history_map_skips_a_failing_symbol_without_aborting(self):
        client, _ = self.client(
            [
                json_response({"candles": [{"datetime": 1, "close": 10}]}),
                HttpResponse(404, b"unknown symbol"),
                json_response({"candles": [{"datetime": 1, "close": 20}]}),
            ]
        )
        failures: list[str] = []
        history = client.load_history_map(
            ["GOOD", "BAD", "ALSOGOOD"], on_error=lambda s, e: failures.append(s)
        )
        self.assertEqual(set(history), {"GOOD", "ALSOGOOD"})
        self.assertEqual(failures, ["BAD"])


# --------------------------------------------------------------- portfolio


class PortfolioParsingTests(unittest.TestCase):
    def test_account_number_is_masked_to_four_digits(self):
        self.assertEqual(mask_account("987654321"), "****4321")
        self.assertEqual(mask_account("12"), "****")

    def test_long_position_resolves_cost_basis_and_return(self):
        holding = parse_position(
            {
                "instrument": {"symbol": "AAPL", "assetType": "EQUITY", "description": "Apple"},
                "longQuantity": 10,
                "shortQuantity": 0,
                "averagePrice": 100.0,
                "marketValue": 1200.0,
                "longOpenProfitLoss": 200.0,
                "currentDayProfitLoss": 24.0,
            }
        )
        self.assertEqual(holding.quantity, 10)
        self.assertEqual(holding.cost_basis, 1000.0)
        self.assertAlmostEqual(holding.unrealized_pl_pct, 0.2)
        self.assertAlmostEqual(holding.last_price, 120.0)
        self.assertAlmostEqual(holding.day_pl_pct, 24.0 / 1176.0)

    def test_unrealized_is_derived_when_schwab_omits_it(self):
        holding = parse_position(
            {
                "instrument": {"symbol": "MSFT", "assetType": "EQUITY"},
                "longQuantity": 5,
                "averagePrice": 200.0,
                "marketValue": 1100.0,
            }
        )
        self.assertAlmostEqual(holding.unrealized_pl, 100.0)

    def test_short_position_is_negative_quantity(self):
        holding = parse_position(
            {
                "instrument": {"symbol": "TSLA", "assetType": "EQUITY"},
                "longQuantity": 0,
                "shortQuantity": 4,
                "averagePrice": 250.0,
                "marketValue": -900.0,
            }
        )
        self.assertEqual(holding.quantity, -4)
        self.assertTrue(holding.is_short)

    def test_closed_and_unnamed_positions_are_dropped(self):
        self.assertIsNone(
            parse_position({"instrument": {"symbol": "X"}, "longQuantity": 0})
        )
        self.assertIsNone(parse_position({"instrument": {}, "longQuantity": 5}))

    def test_account_totals_weights_and_concentration(self):
        portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "11112222",
                    "type": "MARGIN",
                    "currentBalances": {"cashBalance": 1000.0, "liquidationValue": 4000.0},
                    "positions": [
                        {
                            "instrument": {"symbol": "AAA", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 100.0,
                            "marketValue": 1500.0,
                            "longOpenProfitLoss": 500.0,
                        },
                        {
                            "instrument": {"symbol": "BBB", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 200.0,
                            "marketValue": 1500.0,
                            "longOpenProfitLoss": -500.0,
                        },
                        {
                            "instrument": {"symbol": "SWVXX", "assetType": "CASH_EQUIVALENT"},
                            "longQuantity": 1,
                            "averagePrice": 1.0,
                            "marketValue": 1.0,
                        },
                    ],
                }
            }
        )

        self.assertEqual(portfolio.account_label, "****2222")
        self.assertEqual(len(portfolio.equity_holdings), 2)
        self.assertEqual(portfolio.invested_value, 3000.0)
        self.assertEqual(portfolio.total_cost_basis, 3000.0)
        self.assertEqual(portfolio.unrealized_pl, 0.0)
        self.assertAlmostEqual(portfolio.largest_weight, 0.5)
        self.assertAlmostEqual(portfolio.concentration_index, 0.5)
        self.assertAlmostEqual(portfolio.effective_positions, 2.0)
        self.assertAlmostEqual(portfolio.cash_weight, 0.25)
        self.assertEqual(portfolio.symbols(), ["AAA", "BBB"])

    def test_liquidation_value_falls_back_to_positions_plus_cash(self):
        portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "99998888",
                    "currentBalances": {"cashBalance": 500.0},
                    "positions": [
                        {
                            "instrument": {"symbol": "CCC", "assetType": "EQUITY"},
                            "longQuantity": 1,
                            "averagePrice": 10.0,
                            "marketValue": 100.0,
                        }
                    ],
                }
            }
        )
        self.assertEqual(portfolio.liquidation_value, 600.0)


# -------------------------------------------------------------- indicators


class IndicatorTests(unittest.TestCase):
    def test_short_series_return_none_rather_than_guessing(self):
        short = [1.0, 2.0, 3.0]
        self.assertIsNone(indicators.sma(short, 10))
        self.assertIsNone(indicators.ema(short, 10))
        self.assertIsNone(indicators.rsi(short, 14))
        self.assertIsNone(indicators.macd(short))
        self.assertIsNone(indicators.change_over(short, 10))
        self.assertIsNone(indicators.slope_pct(short, 10))
        self.assertIsNone(indicators.realized_volatility(short, 30))

    def test_simple_moving_average(self):
        self.assertEqual(indicators.sma([1, 2, 3, 4, 5], 5), 3.0)
        self.assertEqual(indicators.sma([1, 2, 3, 4, 5], 2), 4.5)

    def test_ema_reduces_to_the_mean_on_a_flat_series(self):
        self.assertAlmostEqual(indicators.ema([7.0] * 40, 10), 7.0)

    def test_rsi_pins_to_extremes_on_monotonic_series(self):
        self.assertAlmostEqual(indicators.rsi(rising_series(60), 14), 100.0)
        self.assertAlmostEqual(indicators.rsi(falling_series(60), 14), 0.0, places=6)

    def test_rsi_stays_in_range_on_a_choppy_series(self):
        choppy = [100 + (5 if i % 2 else -5) + i * 0.1 for i in range(80)]
        value = indicators.rsi(choppy, 14)
        self.assertTrue(0.0 <= value <= 100.0)

    def test_macd_histogram_is_positive_in_an_uptrend(self):
        result = indicators.macd(rising_series(200))
        self.assertGreater(result.line, 0)
        self.assertAlmostEqual(result.histogram, result.line - result.signal)

    def test_macd_line_is_negative_in_a_downtrend(self):
        self.assertLess(indicators.macd(falling_series(200)).line, 0)

    def test_atr_matches_a_constant_bar_range(self):
        # Every bar spans 2% of a flat 100 price, so ATR must be 2.0.
        flat = candles([100.0] * 40)
        self.assertAlmostEqual(indicators.atr(flat, 14), 2.0, places=6)

    def test_change_over_measures_the_stated_window(self):
        self.assertAlmostEqual(indicators.change_over([100, 101, 102, 103, 104, 110], 5), 0.10)

    def test_range_position_locates_price_within_the_band(self):
        self.assertEqual(indicators.range_position(50, 0, 100), 0.5)
        self.assertEqual(indicators.range_position(0, 0, 100), 0.0)
        self.assertEqual(indicators.range_position(100, 0, 100), 1.0)
        self.assertIsNone(indicators.range_position(50, 50, 50))

    def test_max_drawdown_finds_the_worst_peak_to_trough(self):
        self.assertAlmostEqual(indicators.max_drawdown([100, 120, 60, 90]), -0.5)
        self.assertAlmostEqual(indicators.max_drawdown([1, 2, 3]), 0.0)

    def test_volume_ratio_detects_a_recent_surge(self):
        bars = candles([100.0] * 100)
        for bar in bars[-5:]:
            bar["volume"] = 3_000.0
        self.assertGreater(indicators.volume_ratio(bars, 5, 60), 1.5)

    def test_realized_volatility_is_zero_on_a_flat_series(self):
        self.assertAlmostEqual(indicators.realized_volatility([100.0] * 60, 30), 0.0)

    def test_realized_volatility_is_annualized(self):
        # A perfectly alternating +/-1% series has a known daily deviation.
        series = [100.0]
        for index in range(80):
            series.append(series[-1] * (1.01 if index % 2 == 0 else 1 / 1.01))
        value = indicators.realized_volatility(series, 30)
        self.assertGreater(value, 0.10 * math.sqrt(1))
        self.assertLess(value, 1.0)

    def test_slope_is_positive_in_an_uptrend_and_negative_in_a_downtrend(self):
        self.assertGreater(indicators.slope_pct(rising_series(200), 50), 0)
        self.assertLess(indicators.slope_pct(falling_series(200), 50), 0)


# ----------------------------------------------------------------- signals


class PolicyTests(unittest.TestCase):
    def test_shipped_policy_file_loads(self):
        policy = signals.Policy.load(POLICY_PATH)
        self.assertIn("max_position_weight", policy.risk)
        self.assertIn("add", policy.thresholds)

    def test_missing_policy_file_is_reported(self):
        with self.assertRaises(signals.PolicyError):
            signals.Policy.load(Path("/nonexistent/policy.toml"))

    def test_incomplete_policy_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "policy.toml"
            path.write_text("[risk]\nmax_position_weight = 0.1\n", encoding="utf-8")
            with self.assertRaises(signals.PolicyError) as caught:
                signals.Policy.load(path)
            self.assertIn("missing sections", str(caught.exception))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.policy = signals.Policy.load(POLICY_PATH)

    def holding(self, symbol="AAA", weight=0.05, average_price=100.0, market_value=1000.0,
                unrealized=0.0):
        from connectors.schwab.portfolio import Holding

        holding = Holding(
            symbol=symbol,
            description=symbol,
            asset_type="EQUITY",
            quantity=10,
            average_price=average_price,
            market_value=market_value,
            unrealized_pl=unrealized,
        )
        holding.weight = weight
        return holding

    def test_sustained_uptrend_scores_as_add(self):
        verdict = signals.evaluate(
            self.holding(unrealized=300.0), candles(rising_series(300)), self.policy
        )
        self.assertEqual(verdict.verdict, signals.ADD)
        self.assertGreater(verdict.score, self.policy.thresholds["add"])
        self.assertTrue(verdict.reasons)

    def test_sustained_downtrend_scores_as_exit(self):
        verdict = signals.evaluate(
            self.holding(unrealized=-300.0), candles(falling_series(300)), self.policy
        )
        self.assertIn(verdict.verdict, (signals.TRIM, signals.EXIT))
        self.assertLess(verdict.score, 0)

    def test_every_reason_names_its_point_contribution(self):
        verdict = signals.evaluate(self.holding(), candles(rising_series(300)), self.policy)
        for reason in verdict.reasons:
            self.assertRegex(reason, r"\([-+]\d+\)$")

    def test_overweight_winner_is_trimmed_despite_a_strong_score(self):
        # The whole point of a guardrail: momentum does not excuse position size.
        verdict = signals.evaluate(
            self.holding(weight=0.40, unrealized=5000.0),
            candles(rising_series(300)),
            self.policy,
        )
        self.assertEqual(verdict.verdict, signals.TRIM)
        self.assertTrue(verdict.guardrail_breaches)
        self.assertIn("single-name cap", verdict.guardrail_breaches[0])

    def test_stop_loss_breach_is_reported_as_a_guardrail(self):
        verdict = signals.evaluate(
            self.holding(average_price=100.0, market_value=700.0, unrealized=-300.0),
            candles(rising_series(300)),
            self.policy,
        )
        self.assertTrue(
            any("stop-loss" in breach for breach in verdict.guardrail_breaches)
        )

    def test_missing_history_yields_no_data_rather_than_a_verdict(self):
        verdict = signals.evaluate(self.holding(), [], self.policy)
        self.assertEqual(verdict.verdict, signals.NO_DATA)
        self.assertEqual(verdict.score, 0.0)
        self.assertIn("no price history returned", verdict.data_gaps)
        self.assertTrue(verdict.research_questions)

    def test_short_history_is_scored_but_gaps_are_declared(self):
        verdict = signals.evaluate(self.holding(), candles(rising_series(40)), self.policy)
        self.assertNotEqual(verdict.verdict, signals.NO_DATA)
        self.assertTrue(any("200 sessions" in gap for gap in verdict.data_gaps))

    def test_strong_verdicts_demand_corroboration(self):
        strong = signals.evaluate(self.holding(), candles(rising_series(300)), self.policy)
        self.assertTrue(strong.needs_corroboration)
        self.assertTrue(strong.research_questions)

    def test_research_questions_name_the_symbol(self):
        verdict = signals.evaluate(
            self.holding(symbol="NVDA"), candles(falling_series(300)), self.policy
        )
        self.assertTrue(all("NVDA" in question for question in verdict.research_questions))

    def test_score_is_clamped_to_the_declared_range(self):
        for series in (rising_series(300), falling_series(300)):
            verdict = signals.evaluate(self.holding(), candles(series), self.policy)
            self.assertGreaterEqual(verdict.score, -100.0)
            self.assertLessEqual(verdict.score, 100.0)

    def test_portfolio_evaluation_orders_by_conviction(self):
        portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "11112222",
                    "currentBalances": {"cashBalance": 100.0, "liquidationValue": 2100.0},
                    "positions": [
                        {
                            "instrument": {"symbol": "UP", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 50.0,
                            "marketValue": 1000.0,
                        },
                        {
                            "instrument": {"symbol": "DOWN", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 200.0,
                            "marketValue": 1000.0,
                        },
                    ],
                }
            }
        )
        history = {
            "UP": candles(rising_series(300)),
            "DOWN": candles(falling_series(300)),
        }
        verdicts = signals.evaluate_portfolio(portfolio, history, self.policy)
        self.assertEqual([v.symbol for v in verdicts], ["UP", "DOWN"])

    def test_portfolio_alerts_catch_book_level_breaches(self):
        portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "11112222",
                    "currentBalances": {"cashBalance": 0.0, "liquidationValue": 1000.0},
                    "positions": [
                        {
                            "instrument": {"symbol": "ONLY", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 100.0,
                            "marketValue": 1000.0,
                        }
                    ],
                }
            }
        )
        alerts = signals.portfolio_alerts(portfolio, self.policy)
        joined = " ".join(alerts)
        self.assertIn("Concentration index", joined)
        self.assertIn("Cash is", joined)
        self.assertIn("Largest position", joined)

    def test_a_balanced_book_raises_no_alerts(self):
        positions = [
            {
                "instrument": {"symbol": f"S{i}", "assetType": "EQUITY"},
                "longQuantity": 10,
                "averagePrice": 100.0,
                "marketValue": 1000.0,
            }
            for i in range(10)
        ]
        portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "11112222",
                    "currentBalances": {"cashBalance": 500.0, "liquidationValue": 10_500.0},
                    "positions": positions,
                }
            }
        )
        self.assertEqual(signals.portfolio_alerts(portfolio, self.policy), [])


# ------------------------------------------------------------------ report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.policy = signals.Policy.load(POLICY_PATH)
        self.portfolio = parse_account(
            {
                "securitiesAccount": {
                    "accountNumber": "44445555",
                    "type": "MARGIN",
                    "currentBalances": {"cashBalance": 2000.0, "liquidationValue": 12_000.0},
                    "positions": [
                        {
                            "instrument": {"symbol": "UP", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 500.0,
                            "marketValue": 6000.0,
                            "longOpenProfitLoss": 1000.0,
                            "currentDayProfitLoss": 50.0,
                        },
                        {
                            "instrument": {"symbol": "DOWN", "assetType": "EQUITY"},
                            "longQuantity": 10,
                            "averagePrice": 500.0,
                            "marketValue": 4000.0,
                            "longOpenProfitLoss": -1000.0,
                            "currentDayProfitLoss": -30.0,
                        },
                    ],
                }
            }
        )
        self.history = {
            "UP": candles(rising_series(300)),
            "DOWN": candles(falling_series(300)),
        }

    def test_brief_contains_every_required_section(self):
        verdicts = signals.evaluate_portfolio(self.portfolio, self.history, self.policy)
        alerts = signals.portfolio_alerts(self.portfolio, self.policy)
        text = report.render_brief(self.portfolio, verdicts, alerts)

        for heading in ("# Portfolio brief", "## Guardrails", "## Actions",
                        "## Portfolio", "## Holdings", "## Research queue"):
            self.assertIn(heading, text)

    def test_brief_masks_the_account_number(self):
        verdicts = signals.evaluate_portfolio(self.portfolio, self.history, self.policy)
        text = report.render_brief(self.portfolio, verdicts, [])
        self.assertIn("****5555", text)
        self.assertNotIn("44445555", text)

    def test_brief_states_that_it_is_not_advice_and_placed_no_orders(self):
        text = report.render_brief(self.portfolio, [], [])
        self.assertIn("not investment advice", text)
        self.assertIn("No order was placed", text)

    def test_missing_values_render_as_a_dash_not_a_zero(self):
        self.assertEqual(report._money(None), "—")
        self.assertEqual(report._pct(None), "—")
        self.assertEqual(report._share(None), "—")
        self.assertEqual(report._num(None), "—")

    def test_returns_are_signed_but_shares_are_not(self):
        # A 47% position weight is a level, not a gain; "+47%" would misread.
        self.assertEqual(report._pct(0.472), "+47.2%")
        self.assertEqual(report._share(0.472), "47.2%")
        self.assertEqual(report._share(0.0), "0.0%")
        self.assertEqual(report._share(-0.527), "-52.7%")

    def test_position_weights_are_never_rendered_with_a_plus_sign(self):
        verdicts = signals.evaluate_portfolio(self.portfolio, self.history, self.policy)
        text = report.render_brief(self.portfolio, verdicts, [])
        self.assertIn("of invested", text)
        self.assertNotIn("+50.0% of invested", text)

    def test_tally_follows_the_conviction_ladder(self):
        def verdict_for(symbol: str, name: str) -> signals.Verdict:
            return signals.Verdict(
                symbol=symbol, verdict=name, score=0.0, metrics=signals.Metrics()
            )

        text = report.render_brief(
            self.portfolio,
            [
                verdict_for("A", signals.EXIT),
                verdict_for("B", signals.ADD),
                verdict_for("C", signals.HOLD),
            ],
            [],
        )
        summary = text.splitlines()[2]
        self.assertEqual(summary, "3 positions scored: 1 add, 1 hold, 1 exit review.")


# --------------------------------------------------------------------- cli


class CliTests(unittest.TestCase):
    def test_parser_exposes_the_documented_commands(self):
        from connectors.schwab.cli import HANDLERS, build_parser

        parser = build_parser()
        for command in ("login", "status", "accounts", "positions", "brief"):
            self.assertIn(command, HANDLERS)
        args = parser.parse_args(["brief", "--json", "--account", "1234"])
        self.assertTrue(args.json)
        self.assertEqual(args.account, "1234")

    def test_no_order_placement_path_exists_in_the_connector(self):
        # The read-only guarantee is load-bearing, so it is asserted, not assumed.
        import connectors.schwab.client as client_module

        source = Path(client_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"POST"', source)
        self.assertNotIn('"DELETE"', source)
        self.assertNotIn('"PUT"', source)
        for name in ("place_order", "cancel_order", "replace_order", "submit_order"):
            self.assertFalse(hasattr(SchwabClient, name), f"{name} must not exist")


if __name__ == "__main__":
    unittest.main()
