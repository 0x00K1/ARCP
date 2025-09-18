"""
Cleanup stale agents from the registry
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .config import config
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


async def start_cleanup_task(registry: AgentRegistry) -> None:
    """Clean up stale agents periodically using configured intervals.

    Stale criterion: agents whose last_seen is older than (AGENT_HEARTBEAT_TIMEOUT * 2).
    Interval: runs every AGENT_CLEANUP_INTERVAL seconds.
    """
    interval_seconds: int = getattr(config, "AGENT_CLEANUP_INTERVAL", 60)
    stale_threshold: timedelta = timedelta(
        seconds=max(60, getattr(config, "AGENT_HEARTBEAT_TIMEOUT", 60) * 2)
    )

    logger.info(
        f"Starting cleanup task: interval={interval_seconds}s, stale_threshold={stale_threshold.total_seconds():.0f}s"
    )

    try:
        while True:
            try:
                # Get all agents using the proper method
                all_agents: Dict[str, Dict[str, Any]] = (
                    await registry.get_all_agent_data()
                )
                stale_agents: List[str] = []
                now_utc = datetime.now(timezone.utc)

                for agent_id, info in all_agents.items():
                    last_seen = info.get("last_seen")
                    if not last_seen:
                        continue

                    # Normalize last_seen to aware datetime in UTC
                    if isinstance(last_seen, str):
                        try:
                            # Support 'Z' suffix
                            last_seen_dt = datetime.fromisoformat(
                                last_seen.replace("Z", "+00:00")
                            )
                        except Exception:
                            # Skip unparseable timestamps
                            continue
                    elif isinstance(last_seen, datetime):
                        last_seen_dt = last_seen
                    else:
                        # Unknown type
                        continue

                    if last_seen_dt.tzinfo is None:
                        # Assume UTC if naive
                        last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

                    if (now_utc - last_seen_dt) > stale_threshold:
                        stale_agents.append(agent_id)

                # Remove stale agents
                for aid in stale_agents:
                    try:
                        await registry.unregister_agent(aid)
                        logger.info(f"Cleaned up stale agent: {aid}")
                    except Exception as unregister_error:
                        logger.warning(
                            f"Failed to unregister stale agent {aid}: {unregister_error}"
                        )

                if stale_agents:
                    logger.debug(
                        f"Cleanup cycle removed {len(stale_agents)} agents; remaining={len(all_agents) - len(stale_agents)}"
                    )
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

            # Sleep until next interval
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled during sleep")
                break
    finally:
        logger.info("Cleanup task stopped")
