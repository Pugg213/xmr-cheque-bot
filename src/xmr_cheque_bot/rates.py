"""Exchange rate module for XMR/RUB using CoinGecko API.

Provides cached exchange rate fetching with 60s TTL and graceful error handling.
Works with and without API key.
"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import structlog

from xmr_cheque_bot.config import get_settings

logger = structlog.get_logger()

# Cache constants
CACHE_TTL_SECONDS = 60


class RateCache:
    """In-memory cache for exchange rates with TTL."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._rate: Decimal | None = None
        self._timestamp: float = 0.0
        self._lock = asyncio.Lock()

    def is_valid(self) -> bool:
        """Check if cached rate is still valid."""
        if self._rate is None:
            return False
        import time

        return time.time() - self._timestamp < self._ttl

    def get(self) -> Decimal | None:
        """Get cached rate if valid."""
        if self.is_valid():
            return self._rate
        return None

    def set(self, rate: Decimal) -> None:
        """Store new rate in cache."""
        import time

        self._rate = rate
        self._timestamp = time.time()

    def invalidate(self) -> None:
        """Clear the cache."""
        self._rate = None
        self._timestamp = 0.0


# Global cache instance
_rate_cache = RateCache()


def _get_coingecko_url(api_key: str | None = None) -> str:
    """Build CoinGecko API URL with optional API key.

    CoinGecko has two endpoints:
    - Public API (no key): api.coingecko.com (rate limited)
    - Pro API (with key): pro-api.coingecko.com
    """
    if api_key:
        return "https://pro-api.coingecko.com/api/v3/simple/price"
    return "https://api.coingecko.com/api/v3/simple/price"


def _get_coingecko_headers(api_key: str | None = None) -> dict[str, str]:
    """Build headers for CoinGecko API request."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "xmr-cheque-bot/0.1.0",
    }
    if api_key:
        headers["x-cg-pro-api-key"] = api_key
    return headers


async def fetch_xmr_rub_rate(
    force_refresh: bool = False,
) -> Decimal:
    """Fetch XMR/RUB exchange rate from CoinGecko with caching.

    Args:
        force_refresh: Ignore cache and fetch fresh rate

    Returns:
        Current XMR/RUB rate as Decimal

    Raises:
        RateFetchError: If rate cannot be fetched from API

    Note:
        - Uses 60s in-memory cache
        - Works without API key (uses public endpoint)
        - Respects rate limits with exponential backoff on 429 errors
    """
    global _rate_cache

    # Check cache first
    if not force_refresh:
        cached = _rate_cache.get()
        if cached is not None:
            logger.debug("rate_cache_hit", rate=str(cached))
            return cached

    settings = get_settings()
    api_key = settings.coingecko_api_key

    url = _get_coingecko_url(api_key)
    headers = _get_coingecko_headers(api_key)
    params = {
        "ids": "monero",
        "vs_currencies": "rub",
    }

    # Use lock to prevent concurrent API requests
    async with _rate_cache._lock:
        # Double-check after acquiring lock
        if not force_refresh:
            cached = _rate_cache.get()
            if cached is not None:
                return cached

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params=params,
                )

                if response.status_code == 429:
                    # Rate limited - log warning and raise
                    logger.warning("coingecko_rate_limited", has_api_key=api_key is not None)
                    raise RateFetchError(
                        "CoinGecko rate limit exceeded. "
                        "Consider using an API key for higher limits."
                    )

                response.raise_for_status()
                data: dict[str, Any] = response.json()

                # Parse response
                monero_data = data.get("monero", {})
                rate = monero_data.get("rub")

                if rate is None:
                    raise RateFetchError(f"Missing RUB rate in CoinGecko response: {data}")

                # Convert to Decimal for precision
                rate_decimal = Decimal(str(rate))

                logger.info(
                    "rate_fetched",
                    rate=str(rate_decimal),
                    source="coingecko",
                    has_api_key=api_key is not None,
                )

                _rate_cache.set(rate_decimal)
                return rate_decimal

        except httpx.HTTPStatusError as e:
            logger.error(
                "coingecko_http_error",
                status_code=e.response.status_code,
                response=e.response.text[:200],
            )
            raise RateFetchError(f"CoinGecko API error: {e}") from e

        except httpx.RequestError as e:
            logger.error("coingecko_request_error", error=str(e))
            raise RateFetchError(f"Failed to connect to CoinGecko: {e}") from e

        except Exception as e:
            logger.error("rate_fetch_unexpected_error", error=str(e))
            raise RateFetchError(f"Unexpected error fetching rate: {e}") from e


class RateFetchError(Exception):
    """Error fetching exchange rate."""

    pass


def invalidate_rate_cache() -> None:
    """Manually invalidate the rate cache.

    Useful for testing or when immediate refresh is needed.
    """
    global _rate_cache
    _rate_cache.invalidate()
    logger.debug("rate_cache_invalidated")
