"""
OpenBalance Fetch Middleware — Cashu-native.

Drop-in replacement for HTTP requests that automatically handles
402 responses by paying with ecash from OpenBalance.

Usage:
    from openbalance_tools import openbalance_fetch

    # One line. Handles registration, ecash, payment, retry.
    response = await openbalance_fetch(
        "https://api.premium-data.example/paid/prices",
        agent_name="my-agent",
    )
"""

from __future__ import annotations

from typing import Optional

import httpx

from .client import OpenBalanceClient


_clients: dict[str, OpenBalanceClient] = {}


async def openbalance_fetch(
    url: str,
    method: str = "GET",
    agent_name: str = "auto-agent",
    api_base: str = "https://api.openbalance.ai/v1",
    **httpx_kwargs,
) -> httpx.Response:
    """
    Fetch a URL with automatic X-Cashu payment.

    1. Registers with OpenBalance if this is the first call
    2. Makes the request
    3. If 402 → pays with ecash from the agent's wallet
    4. Returns the response

    Zero config. Just call it.
    """
    client = await _get_or_create_client(agent_name, api_base)
    return await client.pay_and_fetch(url, method=method, **httpx_kwargs)


async def _get_or_create_client(
    agent_name: str,
    api_base: str,
) -> OpenBalanceClient:
    if agent_name not in _clients:
        client = OpenBalanceClient(api_base=api_base, agent_name=agent_name)
        await client.register(name=agent_name)
        _clients[agent_name] = client
    return _clients[agent_name]
