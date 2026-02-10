"""
Gemini Client Utility

Provides a retry-enabled wrapper for Gemini API calls with exponential backoff
and a global rate limiter to stay within RPM quotas.
"""

import time
import threading
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# --- Global Rate Limiter ---
# Gemini free tier: 15 RPM = 1 call per 4s on average
_MIN_CALL_INTERVAL = 4.0  # seconds between calls
_RETRY_BASE_DELAY = 10.0  # base delay for exponential backoff (10s, 20s, 40s)
_MAX_RETRIES = 3
_last_call_time = 0.0
_rate_lock = threading.Lock()


def configure(min_call_interval: float = None, retry_base_delay: float = None,
              max_retries: int = None):
    """Configure rate limiter settings. Call once at startup from orchestrator."""
    global _MIN_CALL_INTERVAL, _RETRY_BASE_DELAY, _MAX_RETRIES
    if min_call_interval is not None:
        _MIN_CALL_INTERVAL = min_call_interval
    if retry_base_delay is not None:
        _RETRY_BASE_DELAY = retry_base_delay
    if max_retries is not None:
        _MAX_RETRIES = max_retries
    logger.info(f"Gemini rate limiter configured: interval={_MIN_CALL_INTERVAL}s, "
                f"base_delay={_RETRY_BASE_DELAY}s, max_retries={_MAX_RETRIES}")


def _wait_for_rate_limit():
    """Block until enough time has passed since the last Gemini call."""
    global _last_call_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < _MIN_CALL_INTERVAL:
            wait_time = _MIN_CALL_INTERVAL - elapsed
            logger.debug(f"Rate limiter: waiting {wait_time:.1f}s before next Gemini call")
            time.sleep(wait_time)
        _last_call_time = time.time()


def _is_rate_limit_error(e: Exception) -> bool:
    """Check if exception is a rate limit error (429)."""
    # Check exception type name (works with google.api_core.exceptions.ResourceExhausted)
    if 'ResourceExhausted' in type(e).__name__:
        return True
    if 'RateLimitError' in type(e).__name__:
        return True
    # Fallback to string matching for wrapped exceptions
    error_str = str(e).lower()
    return '429' in error_str or 'resource exhausted' in error_str or 'rate limit' in error_str


def call_with_retry(
    call_fn: Callable[[], Any],
    max_retries: int = None,
    base_delay: float = None,
    context: str = ""
) -> Optional[Any]:
    """
    Call a function with exponential backoff retry on rate limit errors.

    All exceptions are caught and logged. Returns None on any failure.
    This allows calling code to use simple `if response:` checks.

    Args:
        call_fn: Zero-argument callable that makes the API call
        max_retries: Maximum number of retry attempts (default from configure())
        base_delay: Base delay in seconds, doubles each retry (default from configure())
        context: Optional context string for logging (e.g., symbol name)

    Returns:
        Result of call_fn if successful, None on any error
    """
    if max_retries is None:
        max_retries = _MAX_RETRIES
    if base_delay is None:
        base_delay = _RETRY_BASE_DELAY

    ctx = f" for {context}" if context else ""
    last_error = None

    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            _wait_for_rate_limit()
            return call_fn()
        except Exception as e:
            last_error = e

            # Only retry on rate limit errors
            if not _is_rate_limit_error(e):
                logger.error(f"Gemini API error{ctx}: {e}")
                return None

            # Don't wait after final attempt
            if attempt < max_retries:
                wait_time = base_delay * (2 ** attempt)  # 10s, 20s, 40s
                logger.warning(
                    f"Rate limited{ctx}, retrying in {wait_time:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)

    # All rate limit retries exhausted
    logger.error(f"Rate limit retries exhausted{ctx}: {last_error}")
    return None
