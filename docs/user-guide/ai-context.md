# AI Context Guide

## Overview

The `ai_context` field is a powerful feature in ARCP that enables AI systems to understand and effectively orchestrate agents. Unlike the `context_brief` field which is designed for human consumption, this field provides detailed, structured information specifically for AI systems to:

> **See Also:** For a complete guide on building agents, see the [Agent Development Guide](agent-development.md).

- **Understand endpoints and APIs**: Detailed information about available endpoints, their schemas, parameters, and response formats
- **Make intelligent routing decisions**: Information about when and how to use the agent
- **Handle orchestration patterns**: Details about async/sync modes, batching, streaming, etc.
- **Integrate seamlessly**: Authentication requirements, error handling, rate limits, and best practices

## Key Characteristics

| Aspect | Description |
|--------|-------------|
| **Purpose** | AI-readable orchestration and integration information |
| **Audience** | AI systems, LLMs, automated orchestrators |
| **Max Length** | 5000 characters |
| **Optional** | Yes, but highly recommended for AI-driven orchestration |
| **Searchable** | Yes, included in semantic vector embeddings |
| **Format** | Free-form text, but structured information recommended |

## What to Include

### 1. Endpoint Documentation

Provide clear information about available endpoints:

```text
Available Endpoints:
- POST /api/v1/process
  Input: {"data": "string", "options": {...}}
  Output: {"result": "processed data", "job_id": "uuid"}
  
- GET /api/v1/status/{job_id}
  Returns: {"status": "pending|completed|failed", "result": {...}}
  
- POST /api/v1/batch
  Input: {"items": [...], "max_concurrent": 10}
  Output: {"batch_id": "uuid", "total": 100}
```

### 2. API Schemas

Include JSON schemas or data structure information:

```text
Request Schema:
{
  "data": {
    "type": "string|object|array",
    "required": true,
    "description": "Data to process"
  },
  "format": {
    "type": "string",
    "enum": ["json", "xml", "csv"],
    "default": "json"
  },
  "async": {
    "type": "boolean",
    "default": false
  }
}
```

### 3. Orchestration Patterns

Explain how to use the agent effectively:

```text
Orchestration Patterns:

1. Synchronous Processing:
   - Use for small payloads (< 1MB)
   - Set "async": false in request
   - Response time: < 5 seconds
   - Best for: Real-time operations

2. Asynchronous Processing:
   - Use for large payloads or long operations
   - Set "async": true in request
   - Poll /status endpoint every 2 seconds
   - Best for: Batch processing, data analysis

3. Streaming:
   - Connect to WebSocket: ws://{endpoint}/stream
   - Send chunks as they're available
   - Receive progressive results
   - Best for: Large datasets, real-time updates
```

### 4. Integration Guidelines

Help AI understand how to integrate:

```text
Integration Guidelines:

Authentication:
- Use Bearer token in Authorization header
- Token obtained via /auth/token endpoint
- Tokens expire after 1 hour

Rate Limits:
- 100 requests/minute for standard operations
- 10 requests/minute for heavy operations (/batch)
- Headers: X-RateLimit-Remaining, X-RateLimit-Reset

Error Handling:
- 4xx errors: Client error, check request format
- 5xx errors: Server error, retry with exponential backoff
- 429 Too Many Requests: Wait for X-RateLimit-Reset

Retries:
- Use exponential backoff: 1s, 2s, 4s, 8s
- Max 5 retry attempts
- Only retry on 5xx and 429 errors
```

### 5. Capabilities Details

Expand on agent capabilities:

```text
Capability: data-processing
- Supported formats: JSON, XML, CSV, Parquet
- Max file size: 100MB
- Processing time: O(n) where n = data size
- Output formats: Same as input or transformed to JSON

Capability: text-analysis
- Languages: English, Spanish, French, Arabic
- Features: sentiment, entities, keywords, summarization
- Max text length: 50,000 characters
- Response includes confidence scores (0-1)
```

### 6. Workflow Examples

Provide example workflows:

```text
Common Workflows:

Workflow 1: Single Item Processing
1. POST /process with data
2. Receive immediate result if sync
3. Poll /status if async

Workflow 2: Batch Processing
1. POST /batch with items array
2. Receive batch_id
3. Poll /batch/status/{batch_id}
4. Retrieve results via GET /batch/results/{batch_id}

Workflow 3: Pipeline Integration
- Use as middleware in data pipeline
- Input from previous stage via /process
- Output to next stage via webhook callback
- Configure webhook in request: {"webhook": "https://..."}
```

## Complete Example

Here's a comprehensive example of `ai_context`:

```python
ai_context = """
# Data Processing Agent - AI Orchestration Guide

## Endpoints

### 1. Process Data
POST /api/v1/process
Content-Type: application/json

Request:
{
    "data": "string or object - data to process",
    "format": "json|xml|csv - input format (default: json)",
    "output_format": "json|xml|csv - output format (default: json)",
    "async": "boolean - async processing (default: false)",
    "options": {
        "validate": "boolean - validate before processing",
        "transform": "string - transformation to apply",
        "callback_url": "string - webhook for async results"
    }
}

Response (sync):
{
    "status": "success|error",
    "result": "processed data",
    "metadata": {
        "processing_time_ms": 150,
        "items_processed": 100
    }
}

Response (async):
{
    "job_id": "uuid-string",
    "status_url": "/api/v1/status/{job_id}",
    "estimated_completion_time": "ISO-8601 datetime"
}

### 2. Check Status
GET /api/v1/status/{job_id}

Response:
{
    "job_id": "uuid-string",
    "status": "pending|processing|completed|failed",
    "progress": 0-100,
    "result": "available when completed",
    "error": "present if failed"
}

### 3. Batch Processing
POST /api/v1/batch
Content-Type: application/json

Request:
{
    "items": ["array of data items to process"],
    "max_concurrent": 10,
    "options": {...}
}

Response:
{
    "batch_id": "uuid-string",
    "total_items": 100,
    "status_url": "/api/v1/batch/status/{batch_id}"
}

## Orchestration Patterns

### Pattern 1: Quick Sync Processing
Use for: Small payloads (< 1MB), real-time needs
Steps:
1. POST to /process with async=false
2. Receive immediate response
Latency: < 5 seconds

### Pattern 2: Async Processing
Use for: Large payloads, complex processing
Steps:
1. POST to /process with async=true
2. Get job_id
3. Poll /status/{job_id} every 2-5 seconds
4. Retrieve result when status=completed
Latency: Variable, check estimated_completion_time

### Pattern 3: Batch Operations
Use for: Multiple items, efficiency needed
Steps:
1. Collect items (up to 1000 per batch)
2. POST to /batch
3. Get batch_id
4. Poll /batch/status/{batch_id}
5. Download results when ready
Efficiency: 10x faster than individual requests

## Authentication & Security
- Method: Bearer token authentication
- Header: Authorization: Bearer {token}
- Token endpoint: POST /auth/token (requires agent credentials)
- Token lifetime: 1 hour
- Refresh: Use refresh_token or re-authenticate

## Rate Limits
- Standard endpoints: 100 req/min
- Batch endpoint: 10 req/min
- Status checks: 300 req/min
- Headers returned: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

## Error Handling
HTTP Status Codes:
- 200: Success
- 400: Invalid request format
- 401: Authentication required
- 403: Insufficient permissions
- 404: Resource not found
- 429: Rate limit exceeded
- 500: Internal server error
- 503: Service temporarily unavailable

Retry Strategy:
- Retry on: 429, 500, 503
- Don't retry on: 400, 401, 403, 404
- Backoff: Exponential (1s, 2s, 4s, 8s, 16s)
- Max retries: 5 attempts

## Data Formats
Supported Input Formats:
- JSON: Recommended, fastest processing
- XML: Supported, slower than JSON
- CSV: Supported for tabular data
- Parquet: Supported for large datasets

Constraints:
- Max payload size: 100MB
- Max items per batch: 1000
- Max text field length: 1,000,000 characters

## Performance Characteristics
- Processing speed: ~1000 items/second
- Concurrent limit: 50 simultaneous requests
- Queue capacity: 10,000 pending jobs
- Typical latency: 100-500ms (sync), 1-60s (async)

## Integration Best Practices
1. Use batch endpoint for > 10 items
2. Implement exponential backoff for retries
3. Cache authentication tokens (1 hour lifetime)
4. Use async mode for payloads > 1MB
5. Include callback_url for async to avoid polling
6. Monitor X-RateLimit headers to avoid 429 errors
7. Implement timeout: 30s for sync, no timeout for async
8. Use HTTPS for all requests
9. Validate data before sending to reduce errors
10. Log job_id for async operations for debugging

## Webhook Callbacks (Async)
When callback_url provided in async request:
- Agent POSTs result to your URL when complete
- Payload: Same as /status response
- Headers: X-Job-ID, X-Agent-ID
- Signature: X-Signature header (HMAC-SHA256)
- Timeout: 10 seconds
- Retries: 3 attempts with exponential backoff

## Monitoring & Debugging
- Health check: GET /health
- Metrics: GET /metrics (Prometheus format)
- Logs: Include X-Request-ID header to trace requests
- Debug mode: Add ?debug=true for verbose responses
"""
```

## Registration Example

```python
from arcp import ARCPClient

# Create detailed AI Context
ai_context = """
Data Processing Agent v2.0

Endpoints:
- POST /process: Process single data item
  Input: {"data": "...", "format": "json|xml|csv"}
  Output: {"result": "...", "metadata": {...}}
  
- POST /batch: Process multiple items
  Input: {"items": [...], "max_concurrent": 10}
  Output: {"batch_id": "...", "status_url": "..."}

Orchestration:
- Use /process for real-time (< 5s response)
- Use /batch for large volumes (> 10 items)
- Async mode available: set "async": true

Rate Limits: 100/min (process), 10/min (batch)
Auth: Bearer token required
Max payload: 100MB per request

Error Handling:
- 429: Wait X-RateLimit-Reset seconds
- 5xx: Retry with exponential backoff
- 4xx: Fix request and retry

Best for: Data transformation, format conversion, validation
"""

# Register agent with AI context
client = ARCPClient("https://arcp.example.com")

agent = await client.register_agent(
    agent_id="data-processor-v2",
    name="Data Processor",
    agent_type="processing",
    endpoint="https://api.example.com",
    capabilities=["data-processing", "transformation", "validation"],
    context_brief="Processes and transforms data",  # Human-readable
    ai_context=ai_context,  # AI-readable
    version="2.0.0",
    owner="Data Team",
    public_key="test-public-key-123456789012345678901234567890",
    communication_mode="remote",
    metadata={"version": "2.0", "stable": True},
    agent_key="your-registration-key",
)

print(f"Registered agent: {agent.agent_id}")
```

## How AI Systems Use This Field

### 1. Semantic Search
The `ai_context` is included in vector embeddings, allowing AI systems to find agents based on:
- Specific endpoint patterns (e.g., "agents with webhook callbacks")
- Technical capabilities (e.g., "agents supporting streaming")
- Integration requirements (e.g., "agents with simple sync APIs")

### 2. Intelligent Agent Selection
AI orchestrators can:
- Compare orchestration patterns across agents
- Select optimal agent based on use case (sync vs async, batch vs single)
- Understand performance characteristics and limitations

### 3. Automatic Integration
AI systems can:
- Generate integration code from endpoint documentation
- Handle authentication automatically
- Implement proper error handling and retries
- Optimize request patterns (batching, async, etc.)

### 4. Runtime Adaptation
AI can:
- Switch between sync/async based on payload size
- Implement proper rate limiting
- Handle errors according to documented patterns
- Monitor and adapt to agent performance

## Best Practices

### ✅ Do's

1. **Be Specific**: Provide exact endpoint paths, schemas, and parameters
2. **Include Examples**: Show request/response examples
3. **Document Patterns**: Explain when to use sync vs async, batch vs single
4. **Detail Limits**: Specify rate limits, payload sizes, timeouts
5. **Error Guidance**: Explain error codes and retry strategies
6. **Performance Info**: Include typical latencies and throughput
7. **Update Regularly**: Keep in sync with actual API changes

### ❌ Don'ts

1. **Don't Duplicate context_brief**: That's for humans, this is for AI
2. **Don't Exceed Limit**: Stay within 5000 characters
3. **Don't Include Secrets**: Never put tokens, keys, or credentials
4. **Don't Be Vague**: "Processes data" isn't helpful; be specific
5. **Don't Omit Constraints**: Always document limits and requirements
6. **Don't Forget Updates**: Outdated info causes integration failures

## Validation

The field is validated to ensure:
- Maximum 5000 characters
- String type only
- Empty strings or whitespace-only treated as `None`
- Must be valid UTF-8 text

## Benefits

1. **Better Discovery**: AI finds the right agent for the task
2. **Faster Integration**: AI understands how to use the agent immediately
3. **Fewer Errors**: Clear documentation reduces integration mistakes
4. **Optimal Usage**: AI can choose the best endpoint/pattern for each situation
5. **Self-Documenting**: Agents describe themselves to AI systems
6. **Future-Proof**: Works with any AI orchestration system

## Summary

The `ai_context` field transforms your agents into self-describing, AI-friendly services. By providing detailed, structured information about endpoints, patterns, and integration guidelines, you enable AI systems to discover, understand, and effectively orchestrate your agents without human intervention.

Think of it as writing documentation specifically for an AI engineer who will integrate your agent into complex workflows. The more detailed and structured your context, the better AI systems can work with your agent.

## 📚 Related Documentation

- **[Agent Development Guide](agent-development.md)** - Complete guide to building ARCP agents
- **[Client Library Guide](client-library.md)** - Using the ARCP client library for integration
- **[API Reference](../api-reference/rest-api.md)** - Complete REST API documentation

