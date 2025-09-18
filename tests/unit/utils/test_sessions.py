"""
Unit tests for session management utilities.

Tests the sessions module which provides session management for dashboard authentication.
"""

from unittest.mock import MagicMock

import pytest

from src.arcp.utils.sessions import (
    clear_session_data,
    create_session_key,
    get_session_info,
    get_token_ref_from_request,
    hash_pin,
    set_session_pin,
    verify_session_pin,
)


@pytest.mark.unit
class TestSessionUtilities:
    """Test session management utilities."""

    def test_create_session_key(self):
        """Test session key creation."""
        key = create_session_key(
            user_id="test_user",
            client_fingerprint="test_fingerprint",
            token_ref="test_token_ref",
        )

        assert isinstance(key, str)
        assert len(key) > 0

        # Same inputs should produce same key
        key2 = create_session_key(
            user_id="test_user",
            client_fingerprint="test_fingerprint",
            token_ref="test_token_ref",
        )
        assert key == key2

        # Different inputs should produce different keys
        key3 = create_session_key(
            user_id="different_user",
            client_fingerprint="test_fingerprint",
            token_ref="test_token_ref",
        )
        assert key != key3

    def test_hash_pin(self):
        """Test PIN hashing."""
        hash1 = hash_pin("1234")
        hash2 = hash_pin("1234")
        hash3 = hash_pin("5678")

        assert isinstance(hash1, str)
        assert hash1 == hash2  # Same PIN should produce same hash
        assert hash1 != hash3  # Different PIN should produce different hash
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_get_token_ref_from_request(self):
        """Test extracting token reference from request."""
        from fastapi import Request

        # Mock request with Authorization header
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test_token_here"}

        token_ref = get_token_ref_from_request(mock_request)

        assert token_ref is not None
        # Should extract some reference from the token
        assert isinstance(token_ref, str)

    def test_get_token_ref_from_request_no_header(self):
        """Test token reference extraction with no auth header."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        token_ref = get_token_ref_from_request(mock_request)
        assert token_ref is None

    def test_verify_session_pin_success(self):
        """Test PIN verification function exists and works with simple case."""
        # Test that the function exists and can be called
        result = verify_session_pin("test_user", "1234")
        # Result will be False since no PIN is set, but function should not crash
        assert result is False

    def test_set_session_pin_exists(self):
        """Test that set_session_pin function exists."""
        # Test that the function exists and can be called without crashing
        try:
            set_session_pin("test_user", "1234")
            # Function should not raise exception
        except Exception as e:
            # If it raises an exception, it should be related to storage, not function signature
            assert "storage" in str(e).lower() or "redis" in str(e).lower()

    def test_get_session_info_exists(self):
        """Test that get_session_info function exists."""
        result = get_session_info("test_user")
        # Should return None for non-existent session but not crash
        assert result is None

    def test_clear_session_data_exists(self):
        """Test that clear_session_data function exists."""
        try:
            clear_session_data("test_user")
            # Function should not raise exception for basic call
        except Exception as e:
            # If it raises an exception, it should be related to storage, not function signature
            assert "storage" in str(e).lower() or "redis" in str(e).lower()
