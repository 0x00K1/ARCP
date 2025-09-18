# Vector Search Unavailable

**Type URI:** `https://arcp.0x001.tech/docs/problems/vector-search-unavailable`  
**HTTP Status:** `500 Internal Server Error`  
**Title:** Vector Search Unavailable

## Description

The vector search service is unavailable, preventing semantic search operations.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/vector-search-unavailable",
  "title": "Vector Search Unavailable",
  "status": 500,
  "detail": "Vector search service is currently unavailable",
  "instance": "/public/search",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_vector123"
}
```

## Resolution

- Check if vector search service is running
- Verify service connectivity
- Use fallback search methods if available