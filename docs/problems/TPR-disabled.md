# Three-Phase Registration Disabled

**Status Code:** 503 Service Unavailable

## Problem Description

The requested TPR is currently disabled in the server configuration.

## Common Causes

1. **TPR Flag Disabled**: The TPR flag for this functionality is turned off
2. **Maintenance Mode**: TPR temporarily disabled during maintenance
3. **Deployment Configuration**: TPR not enabled in this environment
4. **License Restriction**: TPR not available in current license tier

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/tpr-disabled",
  "title": "TPR Disabled",
  "status": 503,
  "detail": "Three-phase registration is not enabled",
  "instance": "/auth/agent/validate_compliance",
  "timestamp": "2026-02-02T02:28:37.818Z"
}
```

## Solutions

### For Three-Phase Registration

If you're trying to use three-phase registration (`/auth/agent/validate_compliance`):

1. **Check Configuration**: Ensure `ARCP_TPR=true` in server configuration
2. **Environment Variables**: Set the feature flag in `.env` file:
   ```bash
   ARCP_TPR=true
   ```
3. **Use Legacy Registration**: Fall back to standard registration endpoint if three-phase is not required

### General Feature Flags

1. **Contact Administrator**: Check with server admin about feature availability
2. **Check Documentation**: Verify feature requirements and prerequisites
3. **Alternative Approaches**: Use alternative endpoints or methods if available

## Related Problems

- [configuration-error](configuration-error.md) - Server configuration issues
- [forbidden](forbidden.md) - Permission-related access denied

## Technical Details

### When This Occurs

- Attempting to use three-phase registration when `ARCP_TPR=false`
- Accessing beta/experimental features not enabled in production
- Using features disabled for security or performance reasons

### Server Configuration

Check server logs for:
```
TPR flag disabled: ARCP_TPR
```

### Best Practices

1. **Check Feature Availability**: Query server capabilities before using advanced features
2. **Graceful Degradation**: Implement fallback to standard endpoints
3. **Configuration Management**: Maintain consistent TPR flags across environments
4. **Documentation**: Document which features require specific configuration
