"""Minimal HTTP layer shared by the OAuth and REST modules.

The connector depends only on the standard library so it can run in a bare
container, and every network call goes through a single injectable
``Transport`` callable so the test suite never touches the internet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.request


@dataclass(frozen=True)
class HttpResponse:
    """A completed HTTP exchange."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


#: ``(method, url, headers, body) -> HttpResponse``
Transport = Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse]


def urllib_transport(timeout: float = 30.0) -> Transport:
    """Build a Transport backed by ``urllib.request``.

    HTTP error statuses are returned as ordinary responses rather than
    raised, so callers can inspect Schwab's JSON error bodies.
    """

    def _send(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        request = urllib.request.Request(
            url, data=body, headers=dict(headers), method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    status=response.status,
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except urllib.error.HTTPError as error:
            return HttpResponse(
                status=error.code,
                body=error.read(),
                headers=dict(error.headers.items()) if error.headers else {},
            )

    return _send


def send_with_retry(
    transport: Transport,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None = None,
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> HttpResponse:
    """Retry throttling and transient upstream failures with backoff.

    Schwab throttles per-app rather than per-account, so a burst of
    per-symbol price-history calls is the usual source of ``429``.
    """
    retryable = {429, 500, 502, 503, 504}
    response = transport(method, url, headers, body)
    delay = 1.0
    for _ in range(max(0, attempts - 1)):
        if response.status not in retryable:
            return response
        sleep(delay)
        delay *= 2
        response = transport(method, url, headers, body)
    return response
