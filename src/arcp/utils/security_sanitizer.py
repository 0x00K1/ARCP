"""
Security response sanitizer to prevent information leakage and input reflection.
"""

import html
import re
from typing import Any, Dict, List


class SecuritySanitizer:
    """Sanitize responses to prevent information leakage and reflection attacks."""

    # Patterns that should be scrubbed from error messages
    SENSITIVE_PATTERNS = [
        r"<[^>]*>",  # HTML tags
        r"javascript:",  # JavaScript URLs
        r"data:",  # Data URLs
        r"file:",  # File URLs
        r"vbscript:",  # VBScript URLs
        r"on\w+\s*=",  # Event handlers
        r"expression\s*\(",  # CSS expressions
        r"@import",  # CSS imports
        r"\.\./",  # Path traversal
        r"\\x[0-9a-fA-F]{2}",  # Hex encoded chars
        r"\\u[0-9a-fA-F]{4}",  # Unicode encoded chars
        r"\\[rnt]",  # Escape sequences
        r"\x00",  # Null bytes
        r"[\x00-\x1f\x7f-\x9f]",  # Control characters
    ]

    # Dangerous strings that should be completely removed
    DANGEROUS_STRINGS = [
        "javascript",
        "vbscript",
        "onload",
        "onerror",
        "onclick",
        "onmouseover",
        "onfocus",
        "onblur",
        "onchange",
        "onsubmit",
        "script",
        "iframe",
        "object",
        "embed",
        "applet",
        "meta",
        "link",
        "style",
        "img",
        "svg",
        "math",
        "details",
        "template",
        "eval",
        "alert",
        "confirm",
        "prompt",
        "document",
        "window",
        "location",
        "cookie",
        "localStorage",
        "sessionStorage",
        "XMLHttpRequest",
        "fetch",
        "import",
        "require",
    ]

    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 200) -> str:
        """
        Sanitize a string value to prevent injection and reflection attacks.

        Args:
            value: The string to sanitize
            max_length: Maximum length of the sanitized string

        Returns:
            Sanitized string safe for inclusion in responses
        """
        if not isinstance(value, str):
            return str(value)[:max_length]

        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length] + "..."

        # HTML encode to prevent XSS
        value = html.escape(value, quote=True)

        # Remove dangerous patterns
        for pattern in cls.SENSITIVE_PATTERNS:
            value = re.sub(pattern, "[FILTERED]", value, flags=re.IGNORECASE)

        # Remove dangerous strings
        for dangerous in cls.DANGEROUS_STRINGS:
            try:
                pattern = rf"\b{re.escape(dangerous)}\b"
                value = re.sub(pattern, "[FILTERED]", value, flags=re.IGNORECASE)
            except re.error:
                # Fallback to conservative replacement if regex fails
                value = value.replace(dangerous.lower(), "[FILTERED]")

        # Replace multiple consecutive filtered markers
        value = re.sub(r"\[FILTERED\](\[FILTERED\])+", "[FILTERED]", value)

        return value

    @classmethod
    def sanitize_error_detail(cls, detail: Any) -> str:
        """
        Sanitize error detail for safe inclusion in HTTP responses.

        Args:
            detail: The error detail to sanitize

        Returns:
            Sanitized error message
        """
        if isinstance(detail, dict):
            # For validation errors, sanitize each field
            sanitized = {}
            for key, value in detail.items():
                safe_key = cls.sanitize_string(str(key), 50)
                if isinstance(value, list):
                    safe_value = [
                        cls.sanitize_string(str(v), 100) for v in value[:3]
                    ]  # Limit to 3 errors
                    if len(value) > 3:
                        safe_value.append("... and more")
                else:
                    safe_value = cls.sanitize_string(str(value), 100)
                sanitized[safe_key] = safe_value
            return str(sanitized)

        elif isinstance(detail, list):
            # Sanitize each item in the list
            sanitized = [cls.sanitize_string(str(item), 100) for item in detail[:3]]
            if len(detail) > 3:
                sanitized.append("... and more")
            return str(sanitized)

        else:
            # Simple string sanitization
            return cls.sanitize_string(str(detail), 200)

    @classmethod
    def create_safe_error_response(
        cls,
        status_code: int,
        error_type: str = "Validation Error",
        user_message: str = None,
        details: Any = None,
    ) -> Dict[str, Any]:
        """
        Create a safe error response that doesn't leak sensitive information.

        Args:
            status_code: HTTP status code
            error_type: Type of error
            user_message: Safe message for the user
            details: Error details to sanitize

        Returns:
            Safe error response dictionary
        """
        response = {
            "error": cls.sanitize_string(error_type, 50),
            "status_code": status_code,
        }

        if user_message:
            response["message"] = cls.sanitize_string(user_message, 200)

        if details:
            response["detail"] = cls.sanitize_error_detail(details)

        # Add timestamp for debugging (but not sensitive info)
        from datetime import datetime

        response["timestamp"] = datetime.now().isoformat()

        return response


# Convenience function for common use cases
def safe_error_response(
    status_code: int, message: str, details: Any = None
) -> Dict[str, Any]:
    """Create a safe error response."""
    return SecuritySanitizer.create_safe_error_response(
        status_code=status_code, user_message=message, details=details
    )


# Lightweight detectors for optional JSON content filtering (non-mutating)
class ContentRiskDetector:
    """Detect risky indicators in JSON-like data structures without mutating them."""

    @staticmethod
    def _string_indicators(value: str) -> List[str]:
        indicators: List[str] = []
        if not isinstance(value, str):
            return indicators
        lower = value.lower()
        # Simple string checks first (fast path)
        for s in SecuritySanitizer.DANGEROUS_STRINGS:
            if s in lower:
                indicators.append(s)
        # Regex-based checks
        for pattern in SecuritySanitizer.SENSITIVE_PATTERNS:
            try:
                if re.search(pattern, value, flags=re.IGNORECASE):
                    indicators.append(pattern)
            except re.error:
                # Ignore invalid patterns
                continue
        # Collapse duplicates
        if indicators:
            seen = set()
            uniq = []
            for it in indicators:
                if it not in seen:
                    uniq.append(it)
                    seen.add(it)
            indicators = uniq
        return indicators[:10]

    @classmethod
    def scan_json_for_risk(cls, data: Any, max_items: int = 2000) -> Dict[str, Any]:
        """Scan JSON-like data for risky indicators.

        Returns dict with keys: flagged (bool), indicators (List[str]).
        Limits traversal to max_items elements for performance.
        """
        indicators: List[str] = []
        count = 0

        def visit(node: Any):
            nonlocal count
            if count >= max_items:
                return
            count += 1
            if isinstance(node, dict):
                for k, v in list(node.items())[:50]:  # constrain breadth per dict
                    if isinstance(k, str):
                        indicators.extend(cls._string_indicators(k))
                    visit(v)
            elif isinstance(node, list):
                for item in node[:100]:  # constrain breadth per list
                    visit(item)
            elif isinstance(node, str):
                indicators.extend(cls._string_indicators(node))
            else:
                # Numbers/booleans/None: nothing to do
                return

        try:
            visit(data)
        except Exception:
            # Fail-safe: no flag if traversal fails
            return {"flagged": False, "indicators": []}

        # Unique and trim indicators
        uniq: List[str] = []
        seen = set()
        for it in indicators:
            if it not in seen:
                uniq.append(it)
                seen.add(it)
        return {"flagged": len(uniq) > 0, "indicators": uniq[:20]}
