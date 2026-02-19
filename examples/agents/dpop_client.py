"""
DPoP-enabled ARCP Client Extension.

This module extends the ARCP client to support DPoP (Demonstrating
Proof-of-Possession) for agents that need to authenticate with ARCP
when DPOP_REQUIRED=true.

Usage:
    from dpop_client import DPoPARCPClient

    # Use instead of regular ARCPClient
    client = DPoPARCPClient("http://localhost:8001")

    # All methods automatically include DPoP proofs
    agent = await client.register_agent(
        agent_id="my-agent",
        ...
    )
"""

import logging

# Import original client
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dpop_helper import DPoPGenerator

_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from arcp import ARCPClient  # noqa: E402

logger = logging.getLogger(__name__)


class DPoPARCPClient(ARCPClient):
    """
    ARCP Client with DPoP proof support.

    Extends the standard ARCPClient to automatically generate and include
    DPoP proofs in all authenticated requests. This is required when the
    ARCP server has DPOP_REQUIRED=true.
    """

    def __init__(
        self,
        base_url: str,
        dpop_enabled: bool = True,
        dpop_algorithm: str = "EdDSA",
        **kwargs,
    ):
        """
        Initialize DPoP-enabled ARCP client.

        Args:
            base_url: Base URL of the ARCP server
            dpop_enabled: Whether to generate DPoP proofs (default: True)
            dpop_algorithm: DPoP signing algorithm (default: EdDSA)
            **kwargs: Additional arguments passed to ARCPClient
        """
        super().__init__(base_url, **kwargs)

        self.dpop_enabled = dpop_enabled
        self._dpop_generator: Optional[DPoPGenerator] = None

        if dpop_enabled:
            self._dpop_generator = DPoPGenerator(algorithm=dpop_algorithm)
            logger.info(f"DPoP enabled with algorithm: {dpop_algorithm}")
            logger.info(f"DPoP JWK Thumbprint (jkt): {self._dpop_generator.jkt}")

    def get_dpop_jkt(self) -> Optional[str]:
        """
        Get the JWK Thumbprint (jkt) of the DPoP public key.

        Returns:
            JWK Thumbprint string if DPoP is enabled, None otherwise
        """
        if self._dpop_generator:
            return self._dpop_generator.jkt
        return None

    def _generate_dpop_proof(
        self,
        method: str,
        url: str,
        access_token: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate DPoP proof for a request.

        Args:
            method: HTTP method
            url: Full request URL
            access_token: Access token to bind (for ath claim)

        Returns:
            DPoP proof JWT or None if DPoP is disabled
        """
        if not self.dpop_enabled or not self._dpop_generator:
            return None

        return self._dpop_generator.create_proof(
            method=method,
            uri=url,
            access_token=access_token,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_required: bool = True,
        public_api: bool = False,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with DPoP proof.

        Overrides parent _request to automatically add DPoP header.
        """
        from urllib.parse import urljoin

        # Build full URL for DPoP proof
        url = urljoin(self.base_url, endpoint.lstrip("/"))

        # Prepare headers with DPoP proof
        req_headers = headers.copy() if headers else {}

        # Generate DPoP proof
        access_token = self._access_token if auth_required else None
        dpop_proof = self._generate_dpop_proof(method, url, access_token)

        if dpop_proof:
            req_headers["DPoP"] = dpop_proof
            logger.debug(f"Added DPoP proof for {method} {endpoint}")

        # Call parent request method
        return await super()._request(
            method=method,
            endpoint=endpoint,
            json_data=json_data,
            params=params,
            headers=req_headers,
            auth_required=auth_required,
            public_api=public_api,
        )


# Convenience function for quick usage
def create_dpop_client(
    base_url: str, dpop_enabled: bool = True, **kwargs
) -> DPoPARCPClient:
    """
    Create a DPoP-enabled ARCP client.

    Args:
        base_url: Base URL of the ARCP server
        dpop_enabled: Whether to generate DPoP proofs
        **kwargs: Additional arguments passed to ARCPClient

    Returns:
        DPoPARCPClient instance
    """
    return DPoPARCPClient(base_url, dpop_enabled=dpop_enabled, **kwargs)


if __name__ == "__main__":
    import asyncio

    async def test_dpop_client():
        """Test DPoP client functionality."""
        print("Testing DPoP ARCP Client...")

        client = DPoPARCPClient("http://localhost:8001")
        print(f"DPoP JKT: {client.get_dpop_jkt()}")

        # Generate a test proof
        from urllib.parse import urljoin

        url = urljoin(client.base_url, "/auth/agent/validate_compliance")
        proof = client._generate_dpop_proof("POST", url, "test-token")
        print(f"\nTest DPoP Proof:\n{proof}")

        print("\nDPoP Client test complete!")

    asyncio.run(test_dpop_client())
