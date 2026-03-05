"""Cheque creation limits and validation.

Enforces max active cheques per user and other creation constraints.
Uses Redis schema helpers for storage integration (stubbed where needed).
"""

import structlog

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.redis_schema import ChequeStatus

logger = structlog.get_logger()

# TODO: Import redis client when storage integration is complete
# from xmr_cheque_bot.storage import get_redis_client


class ChequeLimitError(Exception):
    """Error when cheque creation limit is exceeded."""
    
    def __init__(self, message: str, user_id: str, current_count: int, max_allowed: int):
        super().__init__(message)
        self.user_id = user_id
        self.current_count = current_count
        self.max_allowed = max_allowed


class RateLimitError(Exception):
    """Error when rate limit is exceeded."""
    
    def __init__(self, message: str, user_id: str, retry_after: int):
        super().__init__(message)
        self.user_id = user_id
        self.retry_after = retry_after


async def count_active_cheques(user_id: str) -> int:
    """Count active (non-final) cheques for a user.
    
    Active cheques are those in PENDING, MEMPOOL, or CONFIRMING status.
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        Number of active cheques
    
    Note:
        This is a stub implementation. Full implementation will query Redis
        using the user_cheques index and filter by status.
    """
    # TODO: Implement actual Redis query
    # Steps:
    # 1. Get user_cheques index (sorted set of cheque IDs)
    # 2. For each cheque, get status
    # 3. Count those in active states
    
    logger.debug("count_active_cheques_stub", user_id=user_id)
    
    # Stub: return 0 for now
    # In production, this queries Redis
    return 0


async def check_cheque_creation_allowed(user_id: str) -> bool:
    """Check if user can create a new cheque.
    
    Validates:
        1. Max active cheques per user (default: 10)
        2. Rate limit (10 cheques / 10 minutes)
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        True if creation is allowed
    
    Raises:
        ChequeLimitError: If max active cheques exceeded
        RateLimitError: If rate limit exceeded
    
    Example:
        >>> try:
        ...     await check_cheque_creation_allowed("123456")
        ...     # Proceed to create cheque
        ... except ChequeLimitError as e:
        ...     print(f"Limit reached: {e.current_count}/{e.max_allowed}")
    """
    settings = get_settings()
    max_active = settings.max_active_cheques_per_user
    
    # Check 1: Max active cheques
    active_count = await count_active_cheques(user_id)
    
    if active_count >= max_active:
        logger.warning(
            "cheque_limit_exceeded",
            user_id=user_id,
            active_count=active_count,
            max_allowed=max_active,
        )
        raise ChequeLimitError(
            message=f"Maximum {max_active} active cheques allowed. "
                    f"Please wait for existing cheques to complete or expire.",
            user_id=user_id,
            current_count=active_count,
            max_allowed=max_active,
        )
    
    # Check 2: Rate limit (10 cheques / 10 minutes)
    # TODO: Implement actual rate limit check using Redis
    # For now, this is a stub
    rate_limited = await _check_rate_limit(user_id)
    if rate_limited:
        logger.warning(
            "cheque_rate_limited",
            user_id=user_id,
        )
        raise RateLimitError(
            message="Too many cheques created recently. Please wait a few minutes.",
            user_id=user_id,
            retry_after=600,  # 10 minutes
        )
    
    logger.debug(
        "cheque_creation_allowed",
        user_id=user_id,
        active_count=active_count,
        max_allowed=max_active,
    )
    
    return True


async def _check_rate_limit(user_id: str) -> bool:
    """Check if user is rate limited for cheque creation.
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        True if rate limited, False otherwise
    
    Note:
        Stub implementation. Full implementation will:
        1. Check Redis rate limit key (ratelimit:cheque:{user_id})
        2. Increment counter with 10-minute window
        3. Return True if count > 10
    """
    # TODO: Implement actual rate limiting with Redis
    logger.debug("rate_limit_check_stub", user_id=user_id)
    return False


async def record_cheque_creation(user_id: str, cheque_id: str) -> None:
    """Record cheque creation for limit tracking.
    
    Updates:
        - User's cheque index
        - Rate limit counter
    
    Args:
        user_id: Telegram user ID
        cheque_id: Unique cheque identifier
    
    Note:
        Stub implementation. Full implementation will update Redis.
    """
    # TODO: Implement actual Redis updates:
    # 1. Add cheque_id to user_cheques:{user_id} sorted set
    # 2. Increment rate limit counter
    
    logger.debug(
        "record_cheque_creation_stub",
        user_id=user_id,
        cheque_id=cheque_id,
    )


def get_active_statuses() -> set[ChequeStatus]:
    """Get set of statuses considered "active".
    
    Returns:
        Set of active cheque statuses
    """
    return {
        ChequeStatus.PENDING,
        ChequeStatus.MEMPOOL,
        ChequeStatus.CONFIRMING,
    }


def is_status_active(status: ChequeStatus) -> bool:
    """Check if a status is considered active.
    
    Args:
        status: Cheque status to check
    
    Returns:
        True if status is active
    """
    return status in get_active_statuses()
