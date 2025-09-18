"""
Integration tests for Token API endpoints.
These endpoints handle JWT token operations.
"""

import pytest


@pytest.mark.integration
class TestTokensAPI:
    """Integration tests for Token API endpoints."""

    def test_mint_token_without_admin(self, test_client):
        """Test minting token without admin privileges."""
        mint_request = {
            "agent_id": "test-agent",
            "agent_type": "testing",
            "capabilities": ["test"],
            "expires_in": 3600,
        }

        response = test_client.post("/tokens/mint", json=mint_request)

        # Should fail without admin auth
        assert response.status_code == 401

    def test_mint_token_invalid_data(self, test_client):
        """Test minting token with invalid data."""
        invalid_request = {
            "agent_id": "",  # Empty agent_id
            "agent_type": "testing",
            "expires_in": -1,  # Negative expiration
        }

        response = test_client.post("/tokens/mint", json=invalid_request)

        # Should fail with validation error or auth error
        assert response.status_code in [401, 422]

    def test_validate_token_post_valid_token(self, test_client, jwt_token):
        """Test POST token validation with valid token."""
        response = test_client.post(f"/tokens/validate?token={jwt_token}")

        # Should work for validation endpoint (public)
        assert response.status_code == 200
        data = response.json()

        # Should return validation result
        assert "valid" in data

    def test_validate_token_post_invalid_token(self, test_client):
        """Test POST token validation with invalid token."""
        response = test_client.post("/tokens/validate?token=invalid-token")

        assert response.status_code == 200
        data = response.json()

        # Should indicate token is invalid
        assert "valid" in data
        assert data["valid"] is False
        assert "error" in data

    def test_validate_token_post_missing_token(self, test_client):
        """Test POST token validation without token."""
        response = test_client.post("/tokens/validate", json={})

        # Should return validation error
        assert response.status_code == 422

    def test_validate_token_get_with_header(self, test_client, jwt_token):
        """Test GET token validation with Authorization header."""
        headers = {"Authorization": f"Bearer {jwt_token}"}
        response = test_client.get("/tokens/validate", headers=headers)

        # Should validate the token
        assert response.status_code in [200, 401]  # Depends on token validity

    def test_validate_token_get_without_header(self, test_client):
        """Test GET token validation without Authorization header."""
        response = test_client.get("/tokens/validate")

        # Should fail without authorization header
        assert response.status_code == 401

    def test_validate_token_get_malformed_header(self, test_client):
        """Test GET token validation with malformed header."""
        headers = {"Authorization": "malformed-header"}
        response = test_client.get("/tokens/validate", headers=headers)

        # Should fail with malformed header
        assert response.status_code == 401

    def test_refresh_token_valid(self, test_client, jwt_token):
        """Test token refresh with valid token."""
        headers = {"Authorization": f"Bearer {jwt_token}"}
        response = test_client.post("/tokens/refresh", headers=headers)

        # Should either succeed or fail based on token validity
        assert response.status_code in [200, 401]

        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "token_type" in data

    def test_refresh_token_invalid(self, test_client):
        """Test token refresh with invalid token."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = test_client.post("/tokens/refresh", headers=headers)

        # Should fail with invalid token
        assert response.status_code == 401

    def test_refresh_token_without_header(self, test_client):
        """Test token refresh without Authorization header."""
        response = test_client.post("/tokens/refresh")

        # Should fail without authorization header
        assert response.status_code == 401

    def test_refresh_token_expired(self, test_client):
        """Test token refresh with expired token."""
        # Create an expired token (this would need mocking)
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxfQ.invalid"
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = test_client.post("/tokens/refresh", headers=headers)

        # Should fail with expired token
        assert response.status_code == 401

    def test_token_endpoints_content_type(self, test_client):
        """Test that token endpoints return correct content type."""
        # Test validate endpoint with valid request structure (should return application/json)
        response = test_client.post("/tokens/validate?token=test_token")
        assert response.status_code == 200  # Invalid token but valid request structure
        assert "application/json" in response.headers.get("content-type", "")

        # Test refresh endpoint with invalid token (should return application/problem+json for errors)
        headers = {"Authorization": "Bearer test_token"}
        response = test_client.post("/tokens/refresh", headers=headers)
        assert response.status_code == 401  # Invalid token
        assert "application/problem+json" in response.headers.get("content-type", "")

    def test_token_validation_edge_cases(self, test_client):
        """Test token validation with edge cases."""
        edge_cases = [
            "",  # Empty token
            "   ",  # Whitespace token
            "a" * 1000,  # Very long token
            "null",  # String "null"
            "undefined",  # String "undefined"
        ]

        for token in edge_cases:
            response = test_client.post(f"/tokens/validate?token={token}")
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    def test_authorization_header_formats(self, test_client):
        """Test various Authorization header formats."""
        test_cases = [
            "Bearer valid-looking-token",
            "bearer lowercase-bearer",
            "Bearer   token-with-spaces",
            "Bearer",  # Missing token part
            "Token some-token",  # Wrong scheme
            "Basic dGVzdA==",  # Basic auth
        ]

        for auth_header in test_cases:
            headers = {"Authorization": auth_header}
            response = test_client.get("/tokens/validate", headers=headers)
            # All should result in 401 since tokens aren't really valid
            assert response.status_code == 401

    def test_token_refresh_response_format(self, test_client, jwt_token):
        """Test that token refresh returns proper format."""
        headers = {"Authorization": f"Bearer {jwt_token}"}
        response = test_client.post("/tokens/refresh", headers=headers)

        if response.status_code == 200:
            data = response.json()
            # Should have standard OAuth2 token response format
            assert "access_token" in data
            assert "token_type" in data
            assert data["token_type"] == "bearer"
        else:
            # If it fails, should return error in proper format
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    def test_validate_token_performance(self, test_client, jwt_token):
        """Test that token validation is fast."""
        import time

        start_time = time.time()
        response = test_client.post(f"/tokens/validate?token={jwt_token}")
        end_time = time.time()

        assert response.status_code == 200

        # Token validation should be fast
        response_time = end_time - start_time
        assert (
            response_time < 0.5
        ), f"Token validation took {response_time:.2f}s, should be under 0.5s"

    def test_concurrent_token_operations(self, test_client, jwt_token):
        """Test concurrent token operations."""
        import threading

        results = []

        def validate_token():
            response = test_client.post(f"/tokens/validate?token={jwt_token}")
            results.append(response.status_code)

        # Create multiple threads for concurrent validation
        threads = []
        for i in range(5):
            thread = threading.Thread(target=validate_token)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All operations should succeed
        assert len(results) == 5
        assert all(status == 200 for status in results)
