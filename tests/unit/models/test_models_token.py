"""
Unit tests for ARCP token models.
"""

import pytest
from pydantic import ValidationError

from src.arcp.models.token import TokenMintRequest, TokenResponse


@pytest.mark.unit
class TestTokenMintRequest:
    """Test cases for TokenMintRequest model."""

    def test_token_mint_request_basic(self):
        """Test basic token mint request creation."""
        request = TokenMintRequest(user_id="test-user", agent_id="test-agent-001")

        assert request.user_id == "test-user"
        assert request.agent_id == "test-agent-001"
        assert request.scopes == []
        assert request.role == "user"
        assert request.temp_registration is False

    def test_token_mint_request_with_all_fields(self):
        """Test token mint request with all fields."""
        request = TokenMintRequest(
            user_id="admin-user",
            agent_id="security-agent",
            scopes=["read", "write", "admin"],
            role="admin",
            temp_registration=True,
        )

        assert request.user_id == "admin-user"
        assert request.agent_id == "security-agent"
        assert request.scopes == ["read", "write", "admin"]
        assert request.role == "admin"
        assert request.temp_registration is True

    def test_user_id_validation_strips_whitespace(self):
        """Test user_id validation strips whitespace."""
        request = TokenMintRequest(user_id="  test-user  ", agent_id="test-agent")

        assert request.user_id == "test-user"

    def test_user_id_validation_empty_fails(self):
        """Test user_id validation fails for empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="", agent_id="test-agent")

        assert "user_id cannot be empty" in str(exc_info.value)

    def test_user_id_validation_whitespace_only_fails(self):
        """Test user_id validation fails for whitespace-only strings."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="   ", agent_id="test-agent")

        assert "user_id cannot be empty" in str(exc_info.value)

    def test_user_id_validation_too_short(self):
        """Test user_id validation fails for too short IDs."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="a", agent_id="test-agent")  # Only 1 character

        assert "user_id must be at least 2 characters" in str(exc_info.value)

    def test_user_id_validation_too_long(self):
        """Test user_id validation fails for too long IDs."""
        long_user_id = "a" * 101  # 101 characters, exceeds 100 limit

        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id=long_user_id, agent_id="test-agent")

        assert "user_id too long" in str(exc_info.value)

    def test_user_id_validation_valid_characters(self):
        """Test user_id validation accepts valid characters."""
        valid_user_ids = [
            "test-user",
            "test_user",
            "TestUser123",
            "user@domain.com",
            "user.name",
            "123-456_test@example.org",
        ]

        for user_id in valid_user_ids:
            request = TokenMintRequest(user_id=user_id, agent_id="test-agent")
            assert request.user_id == user_id

    def test_user_id_validation_invalid_characters(self):
        """Test user_id validation rejects invalid characters."""
        invalid_user_ids = [
            "test user",  # space
            "test+user",
            "test/user",
            "test\\user",
            "test=user",
            "test#user",
            "test%user",
            "test&user",
        ]

        for user_id in invalid_user_ids:
            with pytest.raises(ValidationError) as exc_info:
                TokenMintRequest(user_id=user_id, agent_id="test-agent")
            assert "invalid characters" in str(exc_info.value)

    def test_agent_id_validation_strips_whitespace(self):
        """Test agent_id validation strips whitespace."""
        request = TokenMintRequest(user_id="test-user", agent_id="  test-agent  ")

        assert request.agent_id == "test-agent"

    def test_agent_id_validation_empty_fails(self):
        """Test agent_id validation fails for empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="")

        assert "agent_id cannot be empty" in str(exc_info.value)

    def test_agent_id_validation_too_short(self):
        """Test agent_id validation fails for too short IDs."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="ab")  # Only 2 characters

        assert "agent_id must be at least 3 characters" in str(exc_info.value)

    def test_agent_id_validation_too_long(self):
        """Test agent_id validation fails for too long IDs."""
        long_agent_id = "a" * 101  # 101 characters, exceeds 100 limit

        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id=long_agent_id)

        assert "agent_id too long" in str(exc_info.value)

    def test_agent_id_validation_valid_characters(self):
        """Test agent_id validation accepts valid characters."""
        valid_agent_ids = [
            "test-agent",
            "test_agent",
            "TestAgent123",
            "agent-123_test",
            "a1b2c3",
        ]

        for agent_id in valid_agent_ids:
            request = TokenMintRequest(user_id="test-user", agent_id=agent_id)
            assert request.agent_id == agent_id

    def test_agent_id_validation_invalid_characters(self):
        """Test agent_id validation rejects invalid characters."""
        invalid_agent_ids = [
            "test@agent",
            "test agent",  # space
            "test.agent",
            "test+agent",
            "test/agent",
        ]

        for agent_id in invalid_agent_ids:
            with pytest.raises(ValidationError) as exc_info:
                TokenMintRequest(user_id="test-user", agent_id=agent_id)
            assert "invalid characters" in str(exc_info.value)

    def test_scopes_validation_basic(self):
        """Test scopes validation with basic scopes."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            scopes=["read", "write", "admin"],
        )

        assert request.scopes == ["read", "write", "admin"]

    def test_scopes_validation_empty_list(self):
        """Test scopes validation with empty list."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", scopes=[]
        )

        assert request.scopes == []

    def test_scopes_validation_omitted_defaults_to_empty(self):
        """Test scopes validation when omitted defaults to empty list."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            # scopes omitted, should use default
        )

        assert request.scopes == []

    def test_scopes_validation_strips_whitespace(self):
        """Test scopes validation strips whitespace from scopes."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            scopes=["  read  ", " write ", "admin"],
        )

        assert request.scopes == ["read", "write", "admin"]

    def test_scopes_validation_filters_empty_scopes(self):
        """Test scopes validation filters out empty scopes."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            scopes=["read", "", "  ", "write", "admin"],
        )

        assert request.scopes == ["read", "write", "admin"]

    def test_scopes_validation_too_many_scopes(self):
        """Test scopes validation fails for too many scopes."""
        too_many_scopes = [f"scope{i}" for i in range(51)]  # 51 scopes

        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                scopes=too_many_scopes,
            )

        assert "too many scopes" in str(exc_info.value)

    def test_scopes_validation_scope_too_long(self):
        """Test scopes validation fails for too long scopes."""
        long_scope = "a" * 101  # 101 characters, exceeds 100 limit

        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user", agent_id="test-agent", scopes=[long_scope]
            )

        assert "scope too long" in str(exc_info.value)

    def test_scopes_validation_non_string_scope(self):
        """Test scopes validation fails for non-string scopes."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                scopes=["read", 123, "write"],  # 123 is not a string
            )

        assert "Input should be a valid string" in str(exc_info.value)

    def test_scopes_validation_valid_characters(self):
        """Test scopes validation accepts valid characters."""
        valid_scopes = [
            "read",
            "write",
            "admin",
            "data.read",
            "api:write",
            "system_admin",
            "user-management",
        ]

        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", scopes=valid_scopes
        )

        assert request.scopes == valid_scopes

    def test_scopes_validation_invalid_characters(self):
        """Test scopes validation rejects invalid characters."""
        invalid_scopes = [
            "read write",  # space
            "read@write",
            "read/write",
            "read\\write",
            "read=write",
            "read#write",
        ]

        for invalid_scope in invalid_scopes:
            with pytest.raises(ValidationError) as exc_info:
                TokenMintRequest(
                    user_id="test-user",
                    agent_id="test-agent",
                    scopes=[invalid_scope],
                )
            assert "invalid characters" in str(exc_info.value)

    def test_role_validation_valid_roles(self):
        """Test role validation accepts valid roles."""
        valid_roles = ["user", "admin", "agent"]

        for role in valid_roles:
            request = TokenMintRequest(
                user_id="test-user", agent_id="test-agent", role=role
            )
            assert request.role == role

    def test_role_validation_case_insensitive(self):
        """Test role validation is case insensitive."""
        case_variations = [
            ("USER", "user"),
            ("Admin", "admin"),
            ("AGENT", "agent"),
            ("User", "user"),
        ]

        for input_role, expected_role in case_variations:
            request = TokenMintRequest(
                user_id="test-user", agent_id="test-agent", role=input_role
            )
            assert request.role == expected_role

    def test_role_validation_strips_whitespace(self):
        """Test role validation strips whitespace."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", role="  admin  "
        )

        assert request.role == "admin"

    def test_role_validation_invalid_roles(self):
        """Test role validation rejects invalid roles."""
        invalid_roles = ["superuser", "guest", "moderator", "", "   "]

        for invalid_role in invalid_roles:
            with pytest.raises(ValidationError) as exc_info:
                TokenMintRequest(
                    user_id="test-user",
                    agent_id="test-agent",
                    role=invalid_role,
                )
            # Different error messages for different invalid types
            error_msg = str(exc_info.value)
            assert (
                "role must be one of" in error_msg
                or "role cannot be empty" in error_msg
            )

    def test_temp_registration_validation(self):
        """Test temp_registration validation."""
        # Test True
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", temp_registration=True
        )
        assert request.temp_registration is True

        # Test False
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", temp_registration=False
        )
        assert request.temp_registration is False

    def test_temp_registration_validation_non_boolean_fails(self):
        """Test temp_registration validation fails for non-boolean values."""
        # NOTE: Pydantic automatically coerces common values to booleans
        # Only truly invalid types should raise ValidationError
        invalid_values = [["list"], {"dict": "value"}, object()]

        for invalid_value in invalid_values:
            with pytest.raises(ValidationError) as exc_info:
                TokenMintRequest(
                    user_id="test-user",
                    agent_id="test-agent",
                    temp_registration=invalid_value,
                )
            # Check for general validation error rather than specific message
            assert "validation error" in str(exc_info.value).lower()


@pytest.mark.unit
class TestTokenResponse:
    """Test cases for TokenResponse model."""

    def test_token_response_basic(self):
        """Test basic token response creation."""
        response = TokenResponse(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token",
            expires_in=3600,
        )

        assert (
            response.access_token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"
        )
        assert response.token_type == "bearer"
        assert response.expires_in == 3600

    def test_token_response_with_custom_token_type(self):
        """Test token response with custom token type."""
        response = TokenResponse(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token",
            token_type="Bearer",  # Capital B
            expires_in=7200,
        )

        assert response.token_type == "bearer"  # Should be normalized to lowercase

    def test_access_token_validation_strips_whitespace(self):
        """Test access_token validation strips whitespace."""
        response = TokenResponse(
            access_token="  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token  ",
            expires_in=3600,
        )

        assert (
            response.access_token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"
        )

    def test_access_token_validation_empty_fails(self):
        """Test access_token validation fails for empty tokens."""
        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token="", expires_in=3600)

        assert "access_token cannot be empty" in str(exc_info.value)

    def test_access_token_validation_too_short(self):
        """Test access_token validation fails for too short tokens."""
        short_token = "a" * 15  # 15 characters, below 16 minimum

        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token=short_token, expires_in=3600)

        assert "access_token too short" in str(exc_info.value)

    def test_access_token_validation_too_long(self):
        """Test access_token validation fails for too long tokens."""
        long_token = "a" * 8193  # 8193 characters, exceeds 8192 limit

        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token=long_token, expires_in=3600)

        assert "access_token too long" in str(exc_info.value)

    def test_access_token_validation_minimum_length(self):
        """Test access_token validation accepts minimum length."""
        min_token = "a" * 16  # Exactly 16 characters

        response = TokenResponse(access_token=min_token, expires_in=3600)

        assert response.access_token == min_token

    def test_access_token_validation_maximum_length(self):
        """Test access_token validation accepts maximum length."""
        max_token = "a" * 8192  # Exactly 8192 characters

        response = TokenResponse(access_token=max_token, expires_in=3600)

        assert response.access_token == max_token

    def test_token_type_validation_case_normalization(self):
        """Test token_type validation normalizes case."""
        case_variations = ["bearer", "Bearer", "BEARER", "BeArEr"]

        for token_type in case_variations:
            response = TokenResponse(
                access_token="valid-token-123456",
                token_type=token_type,
                expires_in=3600,
            )
            assert response.token_type == "bearer"

    def test_token_type_validation_strips_whitespace(self):
        """Test token_type validation strips whitespace."""
        response = TokenResponse(
            access_token="valid-token-123456",
            token_type="  bearer  ",
            expires_in=3600,
        )

        assert response.token_type == "bearer"

    def test_token_type_validation_invalid_type(self):
        """Test token_type validation rejects invalid types."""
        invalid_types = ["basic", "digest", "oauth", "jwt", "", "   "]

        for invalid_type in invalid_types:
            with pytest.raises(ValidationError) as exc_info:
                TokenResponse(
                    access_token="valid-token-123456",
                    token_type=invalid_type,
                    expires_in=3600,
                )
            # Different error messages for different invalid types
            error_msg = str(exc_info.value)
            assert (
                "token_type must be 'bearer'" in error_msg
                or "token_type cannot be empty" in error_msg
            )

    def test_expires_in_validation_positive_values(self):
        """Test expires_in validation accepts positive values."""
        valid_expires_in = [1, 60, 3600, 86400, 604800, 2592000, 31536000]

        for expires_in in valid_expires_in:
            response = TokenResponse(
                access_token="valid-token-123456", expires_in=expires_in
            )
            assert response.expires_in == expires_in

    def test_expires_in_validation_zero_fails(self):
        """Test expires_in validation fails for zero."""
        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token="valid-token-123456", expires_in=0)

        assert "expires_in must be positive" in str(exc_info.value)

    def test_expires_in_validation_negative_fails(self):
        """Test expires_in validation fails for negative values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token="valid-token-123456", expires_in=-1)

        assert "expires_in must be positive" in str(exc_info.value)

    def test_expires_in_validation_too_large(self):
        """Test expires_in validation fails for too large values."""
        too_large = 31_536_001  # 365 days + 1 second

        with pytest.raises(ValidationError) as exc_info:
            TokenResponse(access_token="valid-token-123456", expires_in=too_large)

        assert "expires_in too large" in str(exc_info.value)

    def test_expires_in_validation_maximum_allowed(self):
        """Test expires_in validation accepts maximum allowed value."""
        max_expires_in = 31_536_000  # Exactly 365 days

        response = TokenResponse(
            access_token="valid-token-123456", expires_in=max_expires_in
        )

        assert response.expires_in == max_expires_in

    def test_expires_in_validation_non_integer_fails(self):
        """Test expires_in validation fails for non-integer types."""
        # NOTE: Pydantic may automatically coerce some values like "3600" to integers
        # Testing only truly invalid types
        invalid_values = [[3600], {"expires": 3600}, object()]

        for invalid_value in invalid_values:
            with pytest.raises(ValidationError) as exc_info:
                TokenResponse(
                    access_token="valid-token-123456", expires_in=invalid_value
                )
            # Check for general validation error rather than specific message
            assert "validation error" in str(exc_info.value).lower()

    def test_complete_token_response_scenarios(self):
        """Test complete token response scenarios."""
        # Short-lived token
        short_response = TokenResponse(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.short.token",
            expires_in=300,  # 5 minutes
        )
        assert short_response.expires_in == 300

        # Long-lived token
        long_response = TokenResponse(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.long.token",
            expires_in=2592000,  # 30 days
        )
        assert long_response.expires_in == 2592000

        # Verify default token type
        assert short_response.token_type == "bearer"
        assert long_response.token_type == "bearer"


@pytest.mark.unit
class TestTokenMintRequestNewFields:
    """Test cases for new fields in TokenMintRequest model."""

    # Tests for agent_type field
    def test_agent_type_validation_valid(self):
        """Test agent_type validation with valid values."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_type="testing"
        )
        assert request.agent_type == "testing"

    def test_agent_type_validation_none(self):
        """Test agent_type validation with None (should be allowed)."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_type=None
        )
        assert request.agent_type is None

    def test_agent_type_validation_strips_whitespace(self):
        """Test agent_type validation strips whitespace."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            agent_type="  automation  ",
        )
        assert request.agent_type == "automation"

    def test_agent_type_validation_empty_string_becomes_none(self):
        """Test agent_type validation converts empty string to None."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_type=""
        )
        assert request.agent_type is None

    def test_agent_type_validation_too_short_fails(self):
        """Test agent_type validation fails for too short values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="test-agent", agent_type="a")
        assert "agent_type must be at least 2 characters" in str(exc_info.value)

    def test_agent_type_validation_too_long_fails(self):
        """Test agent_type validation fails for too long values."""
        long_type = "a" * 51  # 51 characters, exceeds 50 limit
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_type=long_type,
            )
        assert "agent_type too long" in str(exc_info.value)

    def test_agent_type_validation_invalid_characters_fails(self):
        """Test agent_type validation fails for invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_type="test@type",
            )
        assert "agent_type contains invalid characters" in str(exc_info.value)

    def test_agent_type_validation_converts_to_lowercase(self):
        """Test agent_type validation converts to lowercase."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_type="TESTING"
        )
        assert request.agent_type == "testing"

    def test_agent_type_validation_not_string_fails(self):
        """Test agent_type validation fails for non-string values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="test-agent", agent_type=123)
        assert "Input should be a valid string" in str(exc_info.value)

    # Tests for used_key field
    def test_used_key_validation_valid(self):
        """Test used_key validation with valid values."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", used_key="test-key-123"
        )
        assert request.used_key == "test-key-123"

    def test_used_key_validation_none(self):
        """Test used_key validation with None (should be allowed)."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", used_key=None
        )
        assert request.used_key is None

    def test_used_key_validation_strips_whitespace(self):
        """Test used_key validation strips whitespace."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            used_key="  secret-key  ",
        )
        assert request.used_key == "secret-key"

    def test_used_key_validation_empty_string_becomes_none(self):
        """Test used_key validation converts empty string to None."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", used_key=""
        )
        assert request.used_key is None

    def test_used_key_validation_too_short_fails(self):
        """Test used_key validation fails for too short values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="test-agent", used_key="ab")
        assert "used_key must be at least 3 characters" in str(exc_info.value)

    def test_used_key_validation_too_long_fails(self):
        """Test used_key validation fails for too long values."""
        long_key = "a" * 101  # 101 characters, exceeds 100 limit
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user", agent_id="test-agent", used_key=long_key
            )
        assert "used_key too long" in str(exc_info.value)

    def test_used_key_validation_invalid_characters_fails(self):
        """Test used_key validation fails for invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user", agent_id="test-agent", used_key="test#key"
            )
        assert "used_key contains invalid characters" in str(exc_info.value)

    def test_used_key_validation_special_allowed_chars(self):
        """Test used_key validation allows special characters like @, -, ."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            used_key="test@key-123.secret",
        )
        assert request.used_key == "test@key-123.secret"

    def test_used_key_validation_not_string_fails(self):
        """Test used_key validation fails for non-string values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(user_id="test-user", agent_id="test-agent", used_key=456)
        assert "Input should be a valid string" in str(exc_info.value)

    # Tests for agent_key_hash field
    def test_agent_key_hash_validation_valid(self):
        """Test agent_key_hash validation with valid SHA256 hash."""
        valid_hash = "fcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0c"
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            agent_key_hash=valid_hash,
        )
        assert request.agent_key_hash == valid_hash

    def test_agent_key_hash_validation_none(self):
        """Test agent_key_hash validation with None (should be allowed)."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_key_hash=None
        )
        assert request.agent_key_hash is None

    def test_agent_key_hash_validation_strips_whitespace(self):
        """Test agent_key_hash validation strips whitespace."""
        valid_hash = "fcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0c"
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            agent_key_hash=f"  {valid_hash}  ",
        )
        assert request.agent_key_hash == valid_hash

    def test_agent_key_hash_validation_empty_string_becomes_none(self):
        """Test agent_key_hash validation converts empty string to None."""
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", agent_key_hash=""
        )
        assert request.agent_key_hash is None

    def test_agent_key_hash_validation_wrong_length_fails(self):
        """Test agent_key_hash validation fails for wrong length."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_key_hash="fcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0",  # 63 chars
            )
        assert "agent_key_hash must be exactly 64 characters" in str(exc_info.value)

    def test_agent_key_hash_validation_too_long_fails(self):
        """Test agent_key_hash validation fails for too long values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_key_hash="fcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0c1",  # 65 chars
            )
        assert "agent_key_hash must be exactly 64 characters" in str(exc_info.value)

    def test_agent_key_hash_validation_invalid_hex_fails(self):
        """Test agent_key_hash validation fails for non-hexadecimal characters."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_key_hash="gcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0c",  # 'g' is not hex
            )
        assert "agent_key_hash must be a valid hexadecimal string" in str(
            exc_info.value
        )

    def test_agent_key_hash_validation_converts_to_lowercase(self):
        """Test agent_key_hash validation converts to lowercase."""
        upper_hash = "FCDCEF2318095BF2986F4E382113BE3B376588474503738225A68A54D9217F0C"
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            agent_key_hash=upper_hash,
        )
        assert request.agent_key_hash == upper_hash.lower()

    def test_agent_key_hash_validation_not_string_fails(self):
        """Test agent_key_hash validation fails for non-string values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenMintRequest(
                user_id="test-user",
                agent_id="test-agent",
                agent_key_hash=123456789,
            )
        assert "Input should be a valid string" in str(exc_info.value)

    # Tests for combinations of new fields
    def test_all_new_fields_together(self):
        """Test all new fields working together."""
        valid_hash = "fcdcef2318095bf2986f4e382113be3b376588474503738225a68a54d9217f0c"
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            temp_registration=True,
            agent_type="testing",
            used_key="test-key-123",
            agent_key_hash=valid_hash,
        )

        assert request.temp_registration is True
        assert request.agent_type == "testing"
        assert request.used_key == "test-key-123"
        assert request.agent_key_hash == valid_hash

    def test_temp_registration_fields_none(self):
        """Test temp registration with new fields as None."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            temp_registration=True,
            agent_type=None,
            used_key=None,
            agent_key_hash=None,
        )

        assert request.temp_registration is True
        assert request.agent_type is None
        assert request.used_key is None
        assert request.agent_key_hash is None
