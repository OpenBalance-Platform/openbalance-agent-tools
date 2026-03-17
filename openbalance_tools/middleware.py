"""
OpenBalance Fetch Middleware

Drop-in replacement for httpx requests that automatically handles
402 Payment Required responses by routing through OpenBalance.

Usage:
    from openbalance_tools import openbalance_fetch

    # One-liner: hits the URL, pays if needed, returns the response
    response = await openbalance_fetch(
        "https://api.premium-data.example/v1/prices",
        agent_name="my-agent",
    )
"""

from __future__ import annotations

from typing import Optional

import httpx

from .client import OpenBalanceClient


# Module-level client cache (one per agent name)
_clients: dict[str, OpenBalanceClient] = {}


async def openbalance_fetch(
    url: str,
    method: str = "GET",
    agent_name: str = "auto-agent",
    api_base: str = "https://api.openbalance.ai/v1",
    auto_fund: bool = True,
    preferred_rail: Optional[str] = None,
    **httpx_kwargs,
) -> httpx.Response:
    """
    Fetch a URL with automatic 402 handling via OpenBalance.

    1. Makes the request normally
    2. If 402 → registers with OpenBalance (if needed), acquires entitlement
    3. Retries with the auth token attached
    4. Returns the final response

    This is the zero-config entry point. An agent can call this
    without any setup and it handles everything.
    """

    async with httpx.AsyncClient(timeout=30) as http:
        # First attempt
        headers = httpx_kwargs.pop("headers", {})
        resp = await http.request(method, url, headers=headers, **httpx_kwargs)

        if resp.status_code != 402:
            return resp

        # Got a 402 — need to pay via OpenBalance
        client = await _get_or_create_client(agent_name, api_base)

        # Acquire entitlement
        entitlement = await client.acquire(
            service_url=url,
            preferred_rail=preferred_rail,
            auto_fund=auto_fund,
        )

        # Retry with auth headers
        headers.update(client.auth_headers(entitlement))
        resp = await http.request(method, url, headers=headers, **httpx_kwargs)

        return resp


async def _get_or_create_client(
    agent_name: str,
    api_base: str,
) -> OpenBalanceClient:
    """Get or create a cached OpenBalance client for this agent."""
    if agent_name not in _clients:
        client = OpenBalanceClient(api_base=api_base, agent_name=agent_name)
        await client.register(name=agent_name)
        _clients[agent_name] = client
    return _clients[agent_name]
