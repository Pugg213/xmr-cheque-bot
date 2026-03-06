"""Structured logging configuration."""

import logging
import sys
from typing import Any

import structlog

from xmr_cheque_bot.config import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _mask_processor,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Secret masking utilities
#
# NOTE: be careful with overly-broad substring matching (e.g. masking every key
# containing "key" would also mask non-secret fields like "message_key").

SENSITIVE_EXACT_KEYS: set[str] = {
    "password",
    "secret",
    "token",
    "view_key",
    "private_view_key",
    "spend_key",
    "mnemonic",
    "seed",
    "auth",
    "authorization",
    # common app-specific
    "bot_token",
    "view_key_encryption_key",
    "coingecko_api_key",
}

SENSITIVE_SUFFIXES: tuple[str, ...] = (
    "_password",
    "_secret",
    "_token",
    "_key",
)

SENSITIVE_EXCEPTIONS: set[str] = {
    # i18n/message routing uses this commonly; not a secret.
    "message_key",
}


def is_sensitive_key(lower_key: str) -> bool:
    if lower_key in SENSITIVE_EXCEPTIONS:
        return False
    if lower_key in SENSITIVE_EXACT_KEYS:
        return True
    return lower_key.endswith(SENSITIVE_SUFFIXES)


def mask_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values in a dictionary for safer logging."""
    result: dict[str, Any] = {}
    for k, v in data.items():
        lower_key = str(k).lower()
        if is_sensitive_key(lower_key):
            if isinstance(v, str) and len(v) > 8:
                result[k] = v[:4] + "***" + v[-4:]
            else:
                result[k] = "***"
        elif isinstance(v, dict):
            result[k] = mask_sensitive(v)
        elif isinstance(v, list):
            result[k] = [mask_sensitive(item) if isinstance(item, dict) else item for item in v]
        else:
            result[k] = v
    return result


def _mask_processor(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return mask_sensitive(event_dict)
