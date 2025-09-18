# Rate Limit Exceeded

**Type URI:** `https://arcp.0x001.tech/docs/problems/rate-limit-exceeded`  
**HTTP Status:** `429 Too Many Requests`  
**Title:** Rate Limit Exceeded

## Description

This problem occurs when a client exceeds the configured rate limits for API requests.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "Rate limit exceeded: 100 requests per minute",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_rate123",
  "rate_limit": "100/minute",
  "retry_after": 60,
  "current_requests": 101
}
```

## Resolution Steps

### 1. Wait and Retry
```bash
# Wait for the retry-after period
sleep 60
# Then retry the request
```

### 2. Implement Exponential Backoff with ARCP Client
```python
import asyncio
import random
from arcp import ARCPClient, ARCPError

class RateLimitHandler:
    """Helper class to handle rate limiting with ARCP client"""
    
    def __init__(self, client: ARCPClient, max_retries: int = 5):
        self.client = client
        self.max_retries = max_retries
    
    async def make_request_with_backoff(self, operation_func, *args, **kwargs):
        """Execute operation with exponential backoff on rate limits"""
        
        for attempt in range(self.max_retries):
            try:
                return await operation_func(*args, **kwargs)
                
            except ARCPError as e:
                if "rate limit" in str(e).lower() or "429" in str(e):
                    if attempt == self.max_retries - 1:
                        raise ARCPError(f"Max retries exceeded after rate limiting")
                    
                    # Exponential backoff with jitter
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Rate limited, waiting {delay:.2f}s before retry {attempt + 1}")
                    await asyncio.sleep(delay)
                else:
                    # Non-rate-limit error, re-raise immediately
                    raise
        
        raise ARCPError("Unexpected retry loop exit")

# Usage example
async def rate_limit_example():
    async with ARCPClient("http://localhost:8001") as client:
        handler = RateLimitHandler(client, max_retries=5)
        
        try:
            # This operation might hit rate limits
            agents = await handler.make_request_with_backoff(
                client.list_agents
            )
            print(f"Successfully retrieved {len(agents)} agents")
            
        except ARCPError as e:
            print(f"Operation failed even with backoff: {e}")

if __name__ == "__main__":
    asyncio.run(rate_limit_example())
```