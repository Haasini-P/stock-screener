"""
StockMind AI — Upstox HTTP Client
Resilient HTTP client with retry, circuit breaker, rate limiting, and structured logging.
All Upstox REST API calls go through this client.
"""

import asyncio
import time
from typing import Any, Optional

import httpx
from pybreaker import CircuitBreaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Circuit breaker: opens after 5 failures, resets after 60 seconds
upstox_circuit_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="upstox_api",
)


class UpstoxAPIError(Exception):
    """Base exception for Upstox API errors."""

    def __init__(self, status_code: int, message: str, error_code: str = ""):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code
        super().__init__(f"Upstox API Error [{status_code}]: {message}")


class UpstoxRateLimitError(UpstoxAPIError):
    """Rate limit exceeded."""
    pass


class UpstoxAuthError(UpstoxAPIError):
    """Authentication/authorization failure."""
    pass


class UpstoxDataUnavailableError(Exception):
    """Data is unavailable from Upstox."""
    pass


class UpstoxClient:
    """
    Resilient async HTTP client for Upstox REST APIs.

    Features:
    - Connection pooling
    - Automatic retry with exponential backoff
    - Circuit breaker pattern
    - Rate limit handling (429 backoff)
    - Structured logging for every request
    - Timeout configuration
    - Response validation
    """

    BASE_URL = "https://api.upstox.com"
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RATE_LIMIT_REQUESTS_PER_SEC = 25  # Stay under the 50/sec limit

    def __init__(self, access_token: Optional[str] = None, base_url: Optional[str] = None):
        self._access_token = access_token
        # Instance override: order placement/modify/cancel live on a different host
        # (api-hft.upstox.com) than everything else (api.upstox.com).
        if base_url:
            self.BASE_URL = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._request_timestamps: list[float] = []
        self._rate_limit_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(self.DEFAULT_TIMEOUT, connect=10.0),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=30,
                ),
                follow_redirects=True,
            )
        return self._client

    def _get_headers(self, access_token: Optional[str] = None) -> dict[str, str]:
        """Build request headers with authorization."""
        token = access_token or self._access_token
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _rate_limit(self) -> None:
        """Simple rate limiter using sliding window."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            # Remove timestamps older than 1 second
            self._request_timestamps = [
                ts for ts in self._request_timestamps if now - ts < 1.0
            ]
            if len(self._request_timestamps) >= self.RATE_LIMIT_REQUESTS_PER_SEC:
                sleep_time = 1.0 - (now - self._request_timestamps[0])
                if sleep_time > 0:
                    logger.debug("rate_limit_throttle", sleep_seconds=sleep_time)
                    await asyncio.sleep(sleep_time)
            self._request_timestamps.append(time.monotonic())

    @upstox_circuit_breaker
    async def _request(
        self,
        method: str,
        path: str,
        access_token: Optional[str] = None,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Execute an HTTP request to Upstox API with full resilience.

        Returns parsed JSON response.
        Raises UpstoxAPIError on API errors.
        """
        await self._rate_limit()

        client = await self._get_client()
        headers = self._get_headers(access_token)
        start_time = time.monotonic()

        try:
            response = await client.request(
                method=method,
                url=path,
                headers=headers,
                params=params,
                json=json_data,
                timeout=timeout or self.DEFAULT_TIMEOUT,
            )

            latency_ms = (time.monotonic() - start_time) * 1000

            logger.info(
                "upstox_api_request",
                method=method,
                path=path,
                status_code=response.status_code,
                latency_ms=round(latency_ms, 2),
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "2"))
                logger.warning("upstox_rate_limited", retry_after=retry_after, path=path)
                await asyncio.sleep(retry_after)
                raise UpstoxRateLimitError(429, "Rate limit exceeded")

            # Handle auth errors
            if response.status_code in (401, 403):
                raise UpstoxAuthError(
                    response.status_code,
                    f"Authentication failed: {response.text}",
                )

            # Handle server errors
            if response.status_code >= 500:
                raise UpstoxAPIError(
                    response.status_code,
                    f"Server error: {response.text}",
                )

            # Handle client errors
            if response.status_code >= 400:
                try:
                    body = response.json() if response.content else {}
                except ValueError:
                    body = {}
                # Upstox errors look like {"status":"error","errors":[{"errorCode":..,"message":..}]}
                first_error = (body.get("errors") or [{}])[0]
                raise UpstoxAPIError(
                    response.status_code,
                    first_error.get("message") or body.get("message") or response.text,
                    first_error.get("errorCode") or body.get("errorCode", ""),
                )

            # Success
            if not response.content:
                return {}

            return response.json()

        except httpx.TimeoutException as e:
            logger.error("upstox_timeout", path=path, error=str(e))
            raise UpstoxAPIError(408, f"Request timeout: {path}")
        except httpx.ConnectError as e:
            logger.error("upstox_connect_error", path=path, error=str(e))
            raise UpstoxDataUnavailableError(f"Cannot connect to Upstox: {e}")

    async def get(
        self,
        path: str,
        params: Optional[dict] = None,
        access_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a GET request."""
        return await self._request("GET", path, access_token=access_token, params=params)

    async def post(
        self,
        path: str,
        json_data: Optional[dict] = None,
        access_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a POST request."""
        return await self._request("POST", path, access_token=access_token, json_data=json_data)

    async def put(
        self,
        path: str,
        json_data: Optional[dict] = None,
        access_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a PUT request."""
        return await self._request("PUT", path, access_token=access_token, json_data=json_data)

    async def delete(
        self,
        path: str,
        json_data: Optional[dict] = None,
        access_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a DELETE request (optionally with a JSON body, e.g. GTT cancel)."""
        return await self._request("DELETE", path, access_token=access_token, json_data=json_data)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
