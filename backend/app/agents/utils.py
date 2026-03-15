"""Agent utilities."""

import json
import re
from app.core.logger import get_logger

log = get_logger(__name__)

def extract_json(text: str) -> dict:
    """Robustly extract the first JSON object from a string."""
    # Try to find the first '{' and last '}'
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in response.")
    
    json_str = match.group(1)
    
    # Clean up whitespace and potential markdown artifacts
    json_str = json_str.strip()
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # If standard parsing fails, try to handle common tailing text issues
        # by finding the first valid JSON block
        try:
            # Iteratively try to parse shorter and shorter strings from the end
            # until we find a valid JSON object starting from the first '{'
            start_idx = json_str.find('{')
            for i in range(len(json_str), start_idx, -1):
                try:
                    return json.loads(json_str[start_idx:i])
                except json.JSONDecodeError:
                    continue
            raise
        except Exception as e:
            raise ValueError(f"Failed to parse extracted JSON: {str(e)}")

def retry_on_error(retries: int = 2):
    """Decorator to retry an async function on exception."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_err = None
            for i in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    log.warning(f"[{func.__name__}] attempt {i+1}/{retries+1} failed: {e}")
            raise last_err
        return wrapper
    return decorator
