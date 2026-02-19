-- Atomic consume of validation token
-- This script ensures single-use validation tokens by atomically
-- checking and marking a validation result as "used".
--
-- KEYS[1] = val:{validation_id}  -- Redis key for validation result
-- ARGV[1] = now_epoch_seconds    -- Current timestamp for expiration check
--
-- Returns:
--   JSON string with {ok: true, binding: {...}} on success
--   JSON string with {ok: false, error: "ERROR_CODE"} on failure
--
-- Error codes:
--   NO_VALIDATION - validation_id not found in Redis
--   ALREADY_USED  - validation token has been consumed
--   EXPIRED       - validation token has expired

local v = redis.call('GET', KEYS[1])

-- Check if validation exists
if not v then 
    return cjson.encode({ ok=false, error="NO_VALIDATION" }) 
end

-- Parse validation data
local o = cjson.decode(v)

-- Check if already used
if o.used == true then 
    return cjson.encode({ ok=false, error="ALREADY_USED" }) 
end

-- Check expiration
if o.exp ~= nil and tonumber(o.exp) < tonumber(ARGV[1]) then
    return cjson.encode({ ok=false, error="EXPIRED" })
end

-- Mark as used and add consumption timestamp
o.used = true
o.consumed_at = ARGV[1]

-- Update Redis key (keeping original TTL)
redis.call('SET', KEYS[1], cjson.encode(o), 'KEEPTTL')

-- Return success with binding data
return cjson.encode({ ok=true, binding=o.binding })
