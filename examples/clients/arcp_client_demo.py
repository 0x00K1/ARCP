#!/usr/bin/env python3
"""
ARCP Client Comprehensive Demo

This example demonstrates all major features of the ARCP client library:
- Basic discovery and health checks
- Semantic agent search
- Agent registration (with valid credentials)
- Real-time WebSocket monitoring
- Agent connection requests

Perfect for learning ARCP and as a reference implementation.
"""

import asyncio
import logging
import uuid

from arcp import AgentRequirements, ARCPClient, ARCPError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ARCPDemo:
    """Comprehensive ARCP client demonstration"""

    def __init__(self, server_url: str = "http://localhost:8001"):
        self.server_url = server_url
        self.client = None

    async def __aenter__(self):
        self.client = ARCPClient(self.server_url)
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def basic_discovery_demo(self):
        """Demonstrate basic ARCP discovery features"""
        print("\n=== Basic Discovery Demo ===")

        try:
            # 1. Health check
            print("1. Checking server health...")
            health = await self.client.health_check()
            print(f"   Server status: {health.get('status', 'unknown')}")
            print(f"   Version: {health.get('version', 'unknown')}")

            # 2. System information
            print("\n2. Getting system information...")
            info = await self.client.get_system_info()
            print(f"   Service: {info.get('service', 'unknown')}")
            features = info.get("public_api", {}).get("features", [])
            print(f"   Features: {len(features)} available")
            for feature in features[:3]:
                print(f"      • {feature}")

            # 3. Available agent types
            print("\n3. Getting allowed agent types...")
            agent_types = await self.client.get_allowed_agent_types()
            print(f"   Allowed types: {', '.join(agent_types[:5])}...")

            # 4. Discover agents
            print("\n4. Discovering available agents...")
            agents = await self.client.discover_agents(limit=10)
            print(f"   Found {len(agents)} agents:")

            for i, agent in enumerate(agents[:5], 1):
                print(f"     {i}. {agent.name} ({agent.agent_type})")
                print(f"        Status: {agent.status}")
                print(f"        Capabilities: {', '.join(agent.capabilities[:3])}...")
                print(f"        Owner: {agent.owner}")

            # 5. System statistics
            print("\n5. Getting system statistics...")
            stats = await self.client.get_public_stats()
            print(f"   Total agents: {stats.get('total_agents', 0)}")
            print(f"   Alive agents: {stats.get('alive_agents', 0)}")
            print(f"   System status: {stats.get('system_status', 'unknown')}")

            # 6. Server health check
            print("\n6. Performing server health check...")
            health_check = await self.client.health_check()
            print(f"   Health status: {health_check.get('status', 'unknown')}")

            return True

        except ARCPError as e:
            print(f"X Discovery demo failed: {e}")
            return False

    async def semantic_search_demo(self):
        """Demonstrate semantic search capabilities"""
        print("\n=== Semantic Search Demo ===")

        try:
            search_queries = [
                "Find agents that can analyze financial data",
                "I need help with data visualization",
                "Security scanning and vulnerability assessment",
                "Natural language processing and text analysis",
            ]

            for i, query in enumerate(search_queries, 1):
                print(f"\n{i}. Searching: '{query}'")

                results = await self.client.search_agents(
                    query=query,
                    top_k=3,
                    min_similarity=0.3,
                    weighted=True,
                    public_api=True,
                )

                if results:
                    print(f"   Found {len(results)} relevant agents:")
                    for result in results:
                        print(
                            f"      • {result.name} (similarity: {result.similarity:.3f})"
                        )
                        print(
                            f"        Capabilities: {', '.join(result.capabilities[:2])}..."
                        )
                        if result.metrics:
                            print(
                                f"        Reputation: {result.metrics.reputation_score:.2f}"
                            )
                else:
                    print("   No matching agents found")

            return True

        except ARCPError as e:
            print(f"X Search demo failed: {e}")
            return False

    async def agent_details_demo(self):
        """Demonstrate getting detailed agent information"""
        print("\n=== Agent Details Demo ===")

        try:
            # Get agents first
            agents = await self.client.discover_agents(limit=3)
            if not agents:
                print("   No agents available for details demo")
                return True

            for i, agent in enumerate(agents, 1):
                print(f"\n{i}. Detailed info for: {agent.name}")
                try:
                    detailed = await self.client.get_public_agent(agent.agent_id)
                    print(f"   Description: {detailed.context_brief[:100]}...")
                    print(f"   Owner: {detailed.owner}")
                    print(f"   Endpoint: {detailed.endpoint}")
                    print(f"   Last seen: {detailed.last_seen}")
                    print(f"   Version: {detailed.version}")
                    print(f"   Communication: {detailed.communication_mode}")

                    if detailed.metadata:
                        print(
                            f"   Metadata keys: {', '.join(list(detailed.metadata.keys())[:3])}..."
                        )

                except ARCPError as e:
                    print(f"   Warning: Could not get details: {e}")

            return True

        except ARCPError as e:
            print(f"X Agent details demo failed: {e}")
            return False

    async def agent_connection_demo(self):
        """Demonstrate requesting connection to an agent"""
        print("\n=== Agent Connection Demo ===")

        try:
            # Find an agent to connect to
            agents = await self.client.discover_agents(limit=1)
            if not agents:
                print("   No agents available for connection demo")
                return True

            target_agent = agents[0]
            print(f"Target: Requesting connection to: {target_agent.name}")

            # Request connection
            response = await self.client.request_agent_connection(
                agent_id=target_agent.agent_id,
                user_id="demo-user-123",
                user_endpoint="https://demo-app.example.com/callback",
                display_name="Demo User",
                additional_info={
                    "purpose": "Testing ARCP client library",
                    "project": "ARCP Demo",
                    "priority": "low",
                },
            )

            print("   Connection request sent!")
            print(f"   Status: {response.get('status')}")
            print(f"   Message: {response.get('message')}")
            print(f"   Next steps: {response.get('next_steps')}")
            print(f"   Request ID: {response.get('request_id')}")

            return True

        except ARCPError as e:
            print(f"X Connection demo failed: {e}")
            return False

    async def agent_registration_demo(self, agent_key: str = None):
        """Demonstrate agent registration (requires valid agent key)"""
        print("\n=== Agent Registration Demo ===")

        if not agent_key or agent_key == "your-agent-key-here":
            print("   Skipping registration demo - no valid agent key provided")
            print("   Note: To test registration, provide a real agent key:")
            print("      demo.agent_registration_demo('your-real-agent-key')")
            return True

        try:
            # Generate unique agent ID
            agent_id = f"demo-agent-{uuid.uuid4().hex[:8]}"

            print(f"Registering agent: {agent_id}")

            # Register the agent
            agent = await self.client.register_agent(
                agent_id=agent_id,
                name="ARCP Demo Agent",
                agent_type="demo",
                endpoint="https://demo-agent.example.com",
                capabilities=["demo", "testing", "examples", "tutorials"],
                context_brief="A demonstration agent created by the ARCP client demo for testing purposes",
                version="1.0.0",
                owner="ARCP Demo",
                public_key="demo-public-key-for-testing-purposes-only",
                communication_mode="remote",
                metadata={
                    "purpose": "demonstration",
                    "created_by": "arcp_client_demo.py",
                    "environment": "test",
                    "demo_mode": True,
                },
                features=[
                    "api-endpoint",
                    "status-reporting",
                    "demo-responses",
                ],
                max_tokens=1000,
                language_support=["en"],
                rate_limit=10,
                requirements=AgentRequirements(
                    system_requirements=["Python 3.11+"],
                    permissions=["demo-access"],
                    dependencies=["fastapi", "pydantic"],
                    minimum_memory_mb=512,
                    requires_internet=True,
                ),
                policy_tags=["demo", "testing"],
                agent_key=agent_key,
            )

            print("   Agent registered successfully!")
            print(f"   Agent ID: {agent.agent_id}")
            print(f"   Name: {agent.name}")
            print(f"   Status: {agent.status}")
            print(f"   Registered at: {agent.registered_at}")

            # Start heartbeat task
            print("   Starting heartbeat task...")
            heartbeat_task = await self.client.start_heartbeat_task(
                agent_id, interval=15.0
            )

            # Keep alive briefly for demo
            print("   Keeping agent alive for 30 seconds...")
            await asyncio.sleep(30)

            # Stop heartbeat
            heartbeat_task.cancel()
            print("   Heartbeat stopped")

            # Optionally unregister (commented out to keep for testing)
            await self.client.unregister_agent(agent_id)
            print(f"   Agent {agent_id} unregistered")

            return True

        except ARCPError as e:
            print(f"X Registration demo failed: {e}")
            return False

    async def websocket_demo(self, duration: int = 30):
        """Demonstrate real-time WebSocket monitoring"""
        print(f"\n=== WebSocket Demo ({duration}s) ===")

        try:
            print("Connecting to real-time updates...")
            print("Note: This shows live agent registry updates")

            message_count = 0
            start_time = asyncio.get_event_loop().time()

            async for message in self.client.websocket_public():
                current_time = asyncio.get_event_loop().time()
                if current_time - start_time > duration:
                    print(f"   Demo duration ({duration}s) reached")
                    break

                message_count += 1
                msg_type = message.get("type", "unknown")

                print(f"Message {message_count}: {msg_type}")

                if msg_type == "stats_update":
                    data = message.get("data", {})
                    print(f"   System stats: {data.get('total_agents', 0)} agents")
                elif msg_type == "discovery_data":
                    data = message.get("data", {})
                    pagination = data.get("pagination", {})
                    print(
                        f"   Discovery: {pagination.get('total_agents', 0)} total agents"
                    )
                elif msg_type == "agents_update":
                    data = message.get("data", {})
                    print(f"   Agents update: {data.get('total_count', 0)} agents")
                else:
                    print(f"   Data: {str(message)[:100]}...")

                # Brief pause for readability
                await asyncio.sleep(0.1)

            print(f"   WebSocket demo completed ({message_count} messages received)")
            return True

        except KeyboardInterrupt:
            print("\nWebSocket demo stopped by user")
            return True
        except ARCPError as e:
            print(f"X WebSocket demo failed: {e}")
            return False


async def main():
    """Run the comprehensive ARCP client demonstration"""
    print("ARCP Client Comprehensive Demo")
    print("=" * 60)
    print("This demo showcases all major ARCP client features")
    print("Make sure your ARCP server is running on http://localhost:8001")
    print("=" * 60)

    # You can change this URL to point to your ARCP server
    server_url = "http://localhost:8001"

    try:
        async with ARCPDemo(server_url) as demo:
            print(f"\nConnected to ARCP server: {server_url}")

            # Run all demo sections
            demos = [
                ("Basic Discovery", demo.basic_discovery_demo),
                ("Semantic Search", demo.semantic_search_demo),
                ("Agent Details", demo.agent_details_demo),
                ("Agent Connection", demo.agent_connection_demo),
                # ("Agent Registration", lambda: demo.agent_registration_demo("your-agent-key")),
                # ("WebSocket Monitoring", lambda: demo.websocket_demo(30)),
            ]

            results = []
            for name, demo_func in demos:
                print(f"\n{'='*20}")
                try:
                    success = await demo_func()
                    results.append((name, success))
                    if success:
                        print(f"✓ {name} demo completed successfully")
                    else:
                        print(f"X {name} demo failed")
                except Exception as e:
                    print(f"! {name} demo crashed: {e}")
                    results.append((name, False))

                # Small delay between demos
                await asyncio.sleep(1)

            # Summary
            print(f"\n{'='*60}")
            print("DEMO SUMMARY")
            print(f"{'='*60}")

            successful = sum(1 for _, success in results if success)
            total = len(results)

            for name, success in results:
                status = "✓ PASSED" if success else "X FAILED"
                print(f"  {name:<20} {status}")

            print(f"\nResults: {successful}/{total} demos successful")

            if successful == total:
                print("Success: All demos completed successfully!")
                print("\nNext steps:")
                print("   • Try the agent registration demo with a real agent key")
                print("   • Explore the WebSocket monitoring demo")
                print("   • Build your own application using the ARCP client")
            else:
                print("Warning: Some demos failed - check server connection and status")

    except ARCPError as e:
        print(f"X Failed to connect to ARCP server: {e}")
        print("Note: Make sure the ARCP server is running and accessible")
    except Exception as e:
        print(f"! Unexpected error: {e}")

    print("\nThanks for trying the ARCP client demo!")


if __name__ == "__main__":
    # Run the comprehensive demo
    asyncio.run(main())
