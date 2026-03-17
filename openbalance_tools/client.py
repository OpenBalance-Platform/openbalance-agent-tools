"""
OpenBalance Client

The thin SDK that agents use to interact with api.openbalance.ai.
Handles self-registration, wallet management, and entitlement acquisition.

Usage:
    from openbalance_tools import OpenBalanceClient

    client = OpenBalanceClient()
    await client.register("my-research-agent")
    await client.fund("lightning", 10.00)
    token = await client.acquire("https://api.example.com/v1/data")
    # token is ready to use as an auth header
"""

from __future__ import annotations

from typing import Optional

import httpx


OPENBALANCE_API = "https://api.openbalance.ai/v1"


class OpenBalanceClient:
    """
    Lightweight client for the OpenBalance treasury API.
    Designed to be imported into any agent framework.
    """

    def __init__(
        self,
        api_base: str = OPENBALANCE_API,
        agent_id: Optional[str] = None,
        agent_name: str = "unnamed-agent",
    ):
        self.api_base = api_base.rstrip("/")
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._http = httpx.AsyncClient(timeout=30)
        self._entitlement_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Self-registration
    # ------------------------------------------------------------------

    async def register(
        self,
        name: Optional[str] = None,
        description: str = "",
        tier: str = "free",
        callback_url: Optional[str] = None,
    ) -> dict:
        """
        Self-register with OpenBalance. Returns agent_id and wallet info.
        No human signup needed — the agent does this itself on first run.
        """
        resp = await self._http.post(
            f"{self.api_base}/register",
            json={
                "name": name or self.agent_name,
                "description": description,
                "requested_tier": tier,
                "callback_url": callback_url,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.agent_id = data["agent_id"]
        self.agent_name = name or self.agent_name
        return data

    # ------------------------------------------------------------------
    # Funding
    # ------------------------------------------------------------------

    async def fund(self, rail: str, amount_usd: float) -> dict:
        """Fund the wallet on a specific rail. Amount in USD."""
        self._require_registered()
        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/fund",
            json={"rail": rail, "amount_usd": amount_usd},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Entitlement acquisition
    # ------------------------------------------------------------------

    async def acquire(
        self,
        service_url: str,
        preferred_rail: Optional[str] = None,
        auto_fund: bool = True,
    ) -> dict:
        """
        Acquire an entitlement to a paid service.
        Returns the full entitlement including the auth token.
        """
        self._require_registered()

        # Check local cache first
        if service_url in self._entitlement_cache:
            return self._entitlement_cache[service_url]

        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/acquire",
            json={
                "service_url": service_url,
                "preferred_rail": preferred_rail,
                "auto_fund": auto_fund,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._entitlement_cache[service_url] = data
        return data

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    async def delegate(
        self,
        child_agent_id: str,
        service_url: str,
        scopes: Optional[list[str]] = None,
    ) -> dict:
        """Delegate a scoped-down entitlement to a child agent."""
        self._require_registered()
        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/delegate",
            json={
                "child_agent_id": child_agent_id,
                "service_url": service_url,
                "restricted_scopes": scopes,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> dict:
        """Get the agent's full treasury summary."""
        self._require_registered()
        resp = await self._http.get(f"{self.api_base}/agents/{self.agent_id}")
        resp.raise_for_status()
        return resp.json()

    async def entitlements(self, active_only: bool = True) -> list[dict]:
        """List this agent's entitlements."""
        self._require_registered()
        resp = await self._http.get(
            f"{self.api_base}/agents/{self.agent_id}/entitlements",
            params={"active_only": active_only},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Auth header construction
    # ------------------------------------------------------------------

    @staticmethod
    def auth_headers(entitlement: dict) -> dict[str, str]:
        """Build HTTP auth headers from an entitlement token."""
        token_type = entitlement.get("token_type", "")
        token = entitlement.get("token", "")

        if token_type == "macaroon":
            return {"Authorization": f"L402 {token}"}
        elif token_type == "x402_receipt":
            return {"X-Payment-Receipt": token}
        else:
            return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_registered(self):
        if not self.agent_id:
            raise RuntimeError(
                "Agent not registered. Call `await client.register('my-agent')` first."
            )
