"""Shared aiohttp session for all outbound AI calls.

Creating a ``ClientSession`` per request (the previous behaviour) means a fresh DNS
lookup and TLS handshake for every AI call and a lot of socket churn once many users
ask questions at the same time. One session with a connection limit also gives the
bot natural backpressure towards the providers instead of an unlimited fan-out.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import AI_CONNECTION_TIMEOUT, AI_CONNECTION_LIMIT

logger = logging.getLogger(__name__)

_session: aiohttp.ClientSession | None = None
_session_loop: asyncio.AbstractEventLoop | None = None


def _connector() -> aiohttp.TCPConnector:
    return aiohttp.TCPConnector(limit=AI_CONNECTION_LIMIT, ttl_dns_cache=300)


async def get_session() -> aiohttp.ClientSession:
    """Return the process-wide session, (re)created for the running loop."""
    global _session, _session_loop
    loop = asyncio.get_running_loop()

    if _session is not None and (_session.closed or _session_loop is not loop):
        # The session belongs to another (or a finished) event loop: reuse is unsafe.
        await _close_current()

    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=AI_CONNECTION_TIMEOUT, connect=20, sock_read=70),
            connector=_connector(),
        )
        _session_loop = loop
        logger.debug("HTTP session created (connection limit=%s)", AI_CONNECTION_LIMIT)
    return _session


async def _close_current() -> None:
    global _session, _session_loop
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None
    _session_loop = None


async def close_session() -> None:
    """Close the session on shutdown (safe to call more than once)."""
    await _close_current()
