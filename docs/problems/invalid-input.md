# Invalid Input

**Type URI:** `https://arcp.0x001.tech/docs/problems/invalid-input`  
**HTTP Status:** `400 Bad Request`  
**Title:** Invalid Input Data

## Description

This problem occurs when the format or structure of input data is incorrect, but not necessarily a validation rule violation.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/invalid-input",
  "title": "Invalid Input Data",
  "status": 400,
  "detail": "Invalid JSON format in request body",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_input123",
  "input_error": "Expecting ',' delimiter: line 3 column 5 (char 42)"
}
```

## Common Issues

### 1. Malformed JSON
```bash
# Invalid JSON (missing quotes)
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{agent_id: "test"}'  # Wrong - keys need quotes

# Valid JSON
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test"}'  # Correct
```

### 2. Wrong Data Types
```bash
# Wrong data type (string instead of array)
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"capabilities": "processing"}'  # Wrong

# Correct data type
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"capabilities": ["processing"]}'  # Correct
```

## Resolution Steps

### 1. Validate JSON Format
Use a JSON validator to check your request data structure.

### 2. Check Data Types
Ensure all fields match expected types (string, array, object, etc.).

### 3. Review API Documentation
Verify the expected request format for the endpoint.