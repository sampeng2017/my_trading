"""
Gemini Client Utility

Provides a retry-enabled wrapper for Gemini API calls with exponential backoff.
"""

import time
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


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
    max_retries: int = 3,
    base_delay: float = 1.0,
    context: str = ""
) -> Optional[Any]:
    """
    Call a function with exponential backoff retry on rate limit errors.
    
    All exceptions are caught and logged. Returns None on any failure.
    This allows calling code to use simple `if response:` checks.
    
    Args:
        call_fn: Zero-argument callable that makes the API call
        max_retries: Maximum number of retry attempts for rate limits
        base_delay: Base delay in seconds (doubles each retry)
        context: Optional context string for logging (e.g., symbol name)
        
    Returns:
        Result of call_fn if successful, None on any error
    """
    ctx = f" for {context}" if context else ""
    last_error = None
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            return call_fn()
        except Exception as e:
            last_error = e
            
            # Only retry on rate limit errors
            if not _is_rate_limit_error(e):
                logger.error(f"Gemini API error{ctx}: {e}")
                return None
            
            # Don't wait after final attempt
            if attempt < max_retries:
                wait_time = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                logger.warning(
                    f"Rate limited{ctx}, retrying in {wait_time:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
    
    # All rate limit retries exhausted
    logger.error(f"Rate limit retries exhausted{ctx}: {last_error}")
    return None
