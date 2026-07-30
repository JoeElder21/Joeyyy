"""Three-legged OAuth for the Schwab Trader API.

Schwab issues a 30-minute access credential and a 7-day refresh credential.
The refresh window cannot be extended, so a human must re-consent in a
browser once a week; everything in between is automatic.

Token material is written to a git-ignored path with owner-only permissions
and is never logged.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from connectors.schwab.config import (
    ACCESS_RENEW_MARGIN_SECONDS,
    ACCESS_TTL_SECONDS,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    REFRESH_TTL_SECONDS,
    SchwabSettings,
)
from connectors.schwab.transport import HttpResponse, Transport, send_with_retry

Clock = Callable[[], float]


class AuthError(RuntimeError):
    """Raised when consent, exchange, or renewal fails."""


class ReconsentRequired(AuthError):
    """Raised when the 7-day refresh window has closed.

    The only cure is a human re-running the browser consent step.
    """


@dataclass(frozen=True)
class TokenBundle:
    """Credential material plus the two expiry deadlines that govern it."""

    access: str
    refresh: str
    access_expires_at: float
    refresh_expires_at: float
    scope: str = ""
    token_type: str = "Bearer"

    def access_valid(self, now: float, margin: float = ACCESS_RENEW_MARGIN_SECONDS) -> bool:
        return now + margin < self.access_expires_at

    def refresh_valid(self, now: float) -> bool:
        return now < self.refresh_expires_at

    def refresh_seconds_left(self, now: float) -> float:
        return max(0.0, self.refresh_expires_at - now)

    def authorization_header(self) -> dict[str, str]:
        return {"Authorization": f"{self.token_type} {self.access}"}


class TokenStore:
    """Owner-only JSON persistence for a :class:`TokenBundle`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> TokenBundle | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise AuthError(f"Token store at {self.path} is unreadable: {error}") from error
        try:
            return TokenBundle(
                access=payload["access"],
                refresh=payload["refresh"],
                access_expires_at=float(payload["access_expires_at"]),
                refresh_expires_at=float(payload["refresh_expires_at"]),
                scope=payload.get("scope", ""),
                token_type=payload.get("token_type", "Bearer"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError(
                f"Token store at {self.path} is missing expected fields: {error}"
            ) from error

    def save(self, bundle: TokenBundle) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive permissions before any bytes land on disk.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(bundle), handle, indent=2, sort_keys=True)
        os.chmod(self.path, 0o600)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def _basic_auth_header(settings: SchwabSettings) -> dict[str, str]:
    pair = f"{settings.app_key}:{settings.app_secret}".encode()
    return {
        "Authorization": "Basic " + base64.b64encode(pair).decode("ascii"),
        "Content-Type": "application/x-www-form-urlencoded",
    }


def build_authorize_url(settings: SchwabSettings, state: str | None = None) -> tuple[str, str]:
    """Return the consent URL to open in a browser and the ``state`` to verify."""
    nonce = state or secrets.token_urlsafe(16)
    query = urllib.parse.urlencode(
        {
            "client_id": settings.app_key,
            "redirect_uri": settings.callback_url,
            "response_type": "code",
            "state": nonce,
        }
    )
    return f"{OAUTH_AUTHORIZE_URL}?{query}", nonce


def extract_code(redirect_response: str) -> str:
    """Pull the authorization code out of the pasted redirect URL.

    Schwab appends a percent-encoded ``@`` to the code, so the raw query
    string cannot be split by hand. A bare code is passed through unchanged
    to keep the CLI forgiving.
    """
    candidate = redirect_response.strip()
    if not candidate:
        raise AuthError("No redirect URL or authorization code was provided.")
    if "code=" not in candidate:
        return candidate
    query = urllib.parse.urlparse(candidate).query or candidate
    values = urllib.parse.parse_qs(query)
    codes = values.get("code") or []
    if not codes:
        raise AuthError("The redirect URL contained no 'code' parameter.")
    return codes[0]


def verify_state(redirect_response: str, expected: str) -> None:
    """Reject a redirect whose ``state`` does not match the one we issued."""
    query = urllib.parse.urlparse(redirect_response.strip()).query
    returned = urllib.parse.parse_qs(query).get("state") or []
    if not returned or not secrets.compare_digest(returned[0], expected):
        raise AuthError(
            "The redirect 'state' did not match the value this session issued. "
            "Restart the consent step rather than reusing the URL."
        )


def _bundle_from_payload(payload: dict, now: float) -> TokenBundle:
    access = payload.get("access_token") or ""
    refresh = payload.get("refresh_token") or ""
    if not access or not refresh:
        raise AuthError("Schwab returned a token response with no usable credential.")
    lifetime = float(payload.get("expires_in") or ACCESS_TTL_SECONDS)
    return TokenBundle(
        access=access,
        refresh=refresh,
        access_expires_at=now + lifetime,
        refresh_expires_at=now + REFRESH_TTL_SECONDS,
        scope=payload.get("scope", ""),
        token_type=payload.get("token_type", "Bearer"),
    )


def _post_token(
    settings: SchwabSettings,
    form: dict[str, str],
    transport: Transport,
) -> HttpResponse:
    return send_with_retry(
        transport,
        "POST",
        OAUTH_TOKEN_URL,
        _basic_auth_header(settings),
        urllib.parse.urlencode(form).encode("utf-8"),
    )


def exchange_code(
    settings: SchwabSettings,
    redirect_response: str,
    transport: Transport,
    now: Clock = time.time,
) -> TokenBundle:
    """Trade the one-time authorization code for a token bundle."""
    response = _post_token(
        settings,
        {
            "grant_type": "authorization_code",
            "code": extract_code(redirect_response),
            "redirect_uri": settings.callback_url,
        },
        transport,
    )
    if not response.ok:
        raise AuthError(
            f"Authorization code exchange failed with HTTP {response.status}. "
            "Confirm the app status is 'Ready For Use' and that the callback URL "
            "matches the portal registration exactly."
        )
    return _bundle_from_payload(response.json() or {}, now())


def renew(
    settings: SchwabSettings,
    bundle: TokenBundle,
    transport: Transport,
    now: Clock = time.time,
) -> TokenBundle:
    """Exchange the refresh credential for a fresh 30-minute access credential.

    Schwab returns the same refresh credential with an unchanged 7-day
    deadline, so the original deadline is carried forward rather than reset.
    """
    current = now()
    if not bundle.refresh_valid(current):
        raise ReconsentRequired(
            "The 7-day Schwab refresh window has closed. Re-run the browser "
            "consent step: python -m connectors.schwab.cli login"
        )
    response = _post_token(
        settings,
        {"grant_type": "refresh_token", "refresh_token": bundle.refresh},
        transport,
    )
    if response.status in (400, 401):
        raise ReconsentRequired(
            f"Schwab rejected the refresh credential with HTTP {response.status}. "
            "Re-run: python -m connectors.schwab.cli login"
        )
    if not response.ok:
        raise AuthError(f"Token renewal failed with HTTP {response.status}.")
    renewed = _bundle_from_payload(response.json() or {}, current)
    # The refresh deadline belongs to the original consent, not to this call.
    return TokenBundle(
        access=renewed.access,
        refresh=renewed.refresh or bundle.refresh,
        access_expires_at=renewed.access_expires_at,
        refresh_expires_at=bundle.refresh_expires_at,
        scope=renewed.scope or bundle.scope,
        token_type=renewed.token_type,
    )


def ensure_fresh(
    settings: SchwabSettings,
    store: TokenStore,
    transport: Transport,
    now: Clock = time.time,
) -> TokenBundle:
    """Return a usable bundle, renewing and persisting it when required."""
    bundle = store.load()
    if bundle is None:
        raise ReconsentRequired(
            f"No Schwab token found at {store.path}. Run: python -m connectors.schwab.cli login"
        )
    if bundle.access_valid(now()):
        return bundle
    renewed = renew(settings, bundle, transport, now)
    store.save(renewed)
    return renewed
