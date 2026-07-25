"""Runtime settings for the Schwab connector.

Every credential is read from the process environment or a local, ignored
`.env` file. Nothing is defaulted to a real value and nothing is persisted
into the repository tree.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

#: Schwab publishes one OAuth host and two resource hosts under the same
#: domain. These are public, documented endpoints, not credentials.
OAUTH_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"
MARKETDATA_BASE_URL = "https://api.schwabapi.com/marketdata/v1"

#: Schwab only accepts 127.0.0.1 as a callback host for individual
#: developer apps, and the value must match the portal registration byte
#: for byte.
DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"

#: Access tokens live 30 minutes; refresh tokens live 7 days and cannot be
#: extended. The refresh deadline drives the weekly re-consent reminder.
ACCESS_TTL_SECONDS = 30 * 60
REFRESH_TTL_SECONDS = 7 * 24 * 60 * 60

#: Renew the access token this many seconds before it actually expires so a
#: long report run never dies mid-flight.
ACCESS_RENEW_MARGIN_SECONDS = 120


class SettingsError(RuntimeError):
    """Raised when required configuration is absent or malformed."""


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE file. Missing file yields an empty mapping."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name.strip()] = value
    return values


@dataclass(frozen=True)
class SchwabSettings:
    """Resolved connector settings.

    ``app_key`` and ``app_secret`` are the App Key and Secret shown on the
    developer portal for an app whose status is ``Ready For Use``.
    """

    app_key: str
    app_secret: str
    callback_url: str = DEFAULT_CALLBACK_URL
    token_path: Path = REPO_ROOT / "secrets" / "schwab-token.json"
    policy_path: Path = REPO_ROOT / "config" / "portfolio_policy.toml"
    report_dir: Path = REPO_ROOT / "runtime-memory" / "portfolio"
    request_timeout: float = 30.0

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        dotenv_path: Path | None = None,
    ) -> "SchwabSettings":
        """Build settings from the environment, layered over an optional .env.

        Real environment variables win over `.env` entries so a scheduled run
        can inject credentials without touching disk.
        """
        source: dict[str, str] = {}
        source.update(_load_dotenv(dotenv_path or (REPO_ROOT / ".env")))
        source.update(env if env is not None else os.environ)

        key = source.get("SCHWAB_APP_KEY", "").strip()
        secret = source.get("SCHWAB_APP_SECRET", "").strip()
        missing = [
            name
            for name, value in (("SCHWAB_APP_KEY", key), ("SCHWAB_APP_SECRET", secret))
            if not value
        ]
        if missing:
            raise SettingsError(
                "Missing required Schwab settings: "
                + ", ".join(missing)
                + ". See docs/SCHWAB_TRADING_AGENT.md for the setup runbook."
            )

        token_path = source.get("SCHWAB_TOKEN_PATH", "").strip()
        report_dir = source.get("SCHWAB_REPORT_DIR", "").strip()
        policy_path = source.get("SCHWAB_POLICY_PATH", "").strip()

        return cls(
            app_key=key,
            app_secret=secret,
            callback_url=source.get("SCHWAB_CALLBACK_URL", "").strip()
            or DEFAULT_CALLBACK_URL,
            token_path=Path(token_path) if token_path else cls.token_path,
            policy_path=Path(policy_path) if policy_path else cls.policy_path,
            report_dir=Path(report_dir) if report_dir else cls.report_dir,
        )
