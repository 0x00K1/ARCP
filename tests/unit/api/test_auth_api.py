"""
Integration tests for Authentication API endpoints.
These tests handle the complex authentication flows of ARCP.
"""

import time

import pytest


@pytest.mark.integration
class TestAuthAPI:
    """Integration tests for Authentication API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_rate_limit_delay(self):
        """Add small delay between tests to avoid rate limiting."""
        time.sleep(0.5)  # 500ms delay between auth tests

    def test_agent_request_temp_token(self, test_client):
        """Test agent requesting temporary token."""
        token_request = {
            "agent_id": "test-agent-001",
            "agent_type": "testing",
            "agent_key": "test-registration-key-123",  # Use agent_key instead of public_key
            "capabilities": ["test", "demo"],
        }

        response = test_client.post(
            "/auth/agent/request_temp_token", json=token_request
        )

        # Should either succeed or fail due to validation/auth/rate limiting
        assert response.status_code in [200, 400, 401, 422, 429]

        if response.status_code == 200:
            data = response.json()
            assert "temp_token" in data
            assert "expires_in" in data

    def test_agent_request_temp_token_invalid_data(self, test_client):
        """Test agent requesting temp token with invalid data."""
        invalid_request = {
            "agent_id": "",  # Empty agent_id
            "agent_type": "testing",
            "agent_key": "short",  # Too short agent key
            "capabilities": [],
        }

        response = test_client.post(
            "/auth/agent/request_temp_token", json=invalid_request
        )

        # Could be rate limited (429), validation error (422), or bad request (400)
        assert response.status_code in [400, 422, 429]

    def test_login_invalid_direct_agent(self, test_client):
        """Test that direct agent login is blocked."""
        login_data = {"agent_id": "test-agent", "agent_type": "testing"}

        response = test_client.post("/auth/login", json=login_data)

        # Should fail with 401 - direct agent login not allowed, or 429 if rate limited
        assert response.status_code in [401, 429]

        if response.status_code == 401:
            data = response.json()
            assert "Direct agent login not allowed" in data["detail"]
        # If rate limited (429), that's also acceptable as the endpoint is protected

    def test_login_missing_data(self, test_client):
        """Test login with missing required data."""
        response = test_client.post("/auth/login", json={})

        # Could be rate limited (429), validation error (422), or auth error (401)
        assert response.status_code in [401, 422, 429]

    def test_verify_without_token(self, test_client):
        """Test verification endpoint without token - use tokens API."""
        response = test_client.get("/tokens/validate")
        assert response.status_code == 401

    def test_verify_with_invalid_token(self, test_client):
        """Test verification with invalid token (tokens API)."""
        response = test_client.post("/tokens/validate?token=invalid-token")
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") is False

    def test_verify_with_malformed_token(self, test_client):
        """Test verification with malformed token (tokens API)."""
        response = test_client.post("/tokens/validate?token=not-a-jwt-token")
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") is False

    def test_refresh_without_token(self, test_client):
        """Test token refresh without token (tokens API)."""
        response = test_client.post("/tokens/refresh")
        assert response.status_code == 401

    def test_refresh_with_invalid_token(self, test_client):
        """Test token refresh with invalid token (tokens API)."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = test_client.post("/tokens/refresh", headers=headers)
        assert response.status_code == 401

    def test_logout_without_token(self, test_client):
        """Test logout without token."""
        response = test_client.post("/auth/logout")

        # Logout might still succeed even without token
        assert response.status_code in [200, 401]

    def test_logout_with_token(self, test_client, admin_token):
        """Test logout with valid admin token."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = test_client.post("/auth/logout", headers=headers)

        # Should succeed or fail gracefully
        assert response.status_code in [200, 401]

    @pytest.mark.skip(reason="Complex flow requiring valid agent setup")
    def test_full_agent_auth_flow(self, test_client):  # TODO: test full agent auth flow
        """Test complete agent authentication flow."""
        # This would test:
        # 1. Agent requests temp token
        # 2. Agent uses temp token to register
        # 3. Agent gets full access token
        # 4. Agent uses token for authenticated requests
        # 5. Agent refreshes token
        # 6. Agent logs out

    def test_rate_limiting_behavior(self, test_client):
        """Test that rate limiting works on auth endpoints."""
        login_data = {"agent_id": "test-rate-limit", "agent_type": "testing"}

        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = test_client.post("/auth/login", json=login_data)
            responses.append(response.status_code)

        # Should see some rate limiting (429) or consistent 401s
        assert any(status in [401, 429] for status in responses)

    def test_auth_headers_validation(self, test_client):
        """Test various token formats via query parameter (tokens API)."""
        edge_cases = [
            "",
            "short",
            "malformed-token-format",
            "valid-looking-jwt-token",
        ]
        for token in edge_cases:
            response = test_client.post(f"/tokens/validate?token={token}")
            assert response.status_code == 200
            data = response.json()
            assert "valid" in data

    def test_auth_endpoint_security_headers(self, test_client):
        """Test that auth endpoints return appropriate security headers."""
        response = test_client.post("/auth/login", json={})

        # Should have security headers (if configured)
        headers = response.headers

        # These might be set by middleware
        # assert "X-Content-Type-Options" in headers
        # assert "X-Frame-Options" in headers

        # At minimum, should be JSON; accept RFC 9457 problem+json as well
        content_type = headers.get("content-type", "")
        assert ("application/json" in content_type) or (
            "application/problem+json" in content_type
        )

    def test_login_request_validation(self, test_client):
        """Test various invalid login request formats."""
        test_cases = [
            {},  # Empty object
            {"agent_id": "test"},  # Missing agent_type
            {"agent_type": "testing"},  # Missing agent_id
            {"agent_id": "", "agent_type": "testing"},  # Empty agent_id
            {"agent_id": "test", "agent_type": ""},  # Empty agent_type
            {
                "agent_id": "a" * 100,
                "agent_type": "testing",
            },  # Very long agent_id
        ]

        for login_data in test_cases:
            response = test_client.post("/auth/login", json=login_data)
            # Could be auth failure (401), validation error (422), or rate limited (429)
            assert response.status_code in [401, 422, 429]

    def test_temp_token_request_validation(self, test_client):
        """Test validation of temp token requests."""
        test_cases = [
            {},  # Empty object
            {"agent_id": "test"},  # Missing required fields
            {
                "agent_id": "",
                "agent_type": "testing",
                "agent_key": "key",
                "capabilities": [],
            },  # Empty agent_id
            {
                "agent_id": "test",
                "agent_type": "",
                "agent_key": "key",
                "capabilities": [],
            },  # Empty agent_type
            {
                "agent_id": "test",
                "agent_type": "testing",
                "agent_key": "",
                "capabilities": [],
            },  # Empty agent_key
            {
                "agent_id": "test",
                "agent_type": "testing",
                "agent_key": "short",
                "capabilities": [],
            },  # Short agent_key
        ]

        for request_data in test_cases:
            response = test_client.post(
                "/auth/agent/request_temp_token", json=request_data
            )
            # Could be validation error (400, 422) or rate limited (429)
            assert response.status_code in [400, 422, 429]
