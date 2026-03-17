"""
OpenBalance Client — Cashu-native.

The agent holds ecash tokens directly. The client manages:
  - Self-registration (get initial ecash)
  - Minting more ecash (on-ramp via Lightning/USDC/Stripe)
  - Spending ecash at X-Cashu-gated services
  - Token management (splitting, merging)

Usage:
    from openbalance_tools import OpenBalanceClient

    client = OpenBalanceClient()
    await client.register("my-agent")       # get initial ecash
    await client.mint(10000, "lightning")    # mint 10k sats via Lightning

    # Hit a paid API — ecash is sent automatically
    response = await client.pay_and_fetch("https://api.example.com/paid/data")
"""

from __future__ import annotations

import base64
import json
from typing import Optional

import httpx


OPENBALANCE_API = "https://api.openbalance.ai/v1"


class OpenBalanceClient:
    """
    Cashu-native client. Agent holds ecash tokens as bearer instruments.
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

        # The wallet: a list of serialized ecash tokens
        self._tokens: list[str] = []
        self._balance_sats: int = 0

    # ------------------------------------------------------------------
    # Self-registration
    # ------------------------------------------------------------------

    async def register(
        self,
        name: Optional[str] = None,
        description: str = "",
        tier: str = "free",
    ) -> dict:
        """
        Self-register with OpenBalance. Gets initial ecash.
        The ecash IS the wallet — no account needed.
        """
        resp = await self._http.post(
            f"{self.api_base}/register",
            json={
                "name": name or self.agent_name,
                "description": description,
                "requested_tier": tier,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        self.agent_id = data["agent_id"]
        self.agent_name = name or self.agent_name

        # Store the initial ecash token
        if data.get("ecash_token"):
            self._tokens.append(data["ecash_token"])
            self._balance_sats = data.get("ecash_balance_sats", 0)

        return data

    # ------------------------------------------------------------------
    # Minting (on-ramp → ecash)
    # ------------------------------------------------------------------

    async def mint(
        self,
        amount_sats: int,
        on_ramp: str = "lightning",
    ) -> dict:
        """
        Mint more ecash by paying via an on-ramp.
        Returns payment details (invoice/address), then
        call claim() after paying.
        """
        self._require_registered()

        # Step 1: Get a quote
        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/mint/quote",
            json={"amount_sats": amount_sats, "on_ramp": on_ramp},
        )
        resp.raise_for_status()
        quote = resp.json()

        # In a real integration, the agent would pay the invoice here.
        # For development: auto-claim (assumes payment happened)
        return quote

    async def claim(self, quote_id: str) -> dict:
        """Claim ecash after paying a mint quote."""
        self._require_registered()

        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/mint/claim/{quote_id}",
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("ecash_token"):
            self._tokens.append(data["ecash_token"])
            self._balance_sats += data.get("amount_sats", 0)

        return data

    async def mint_and_claim(
        self,
        amount_sats: int,
        on_ramp: str = "lightning",
    ) -> dict:
        """Convenience: mint + claim in one call (for dev/testing)."""
        quote = await self.mint(amount_sats, on_ramp)
        return await self.claim(quote["quote_id"])

    # ------------------------------------------------------------------
    # Spending (X-Cashu)
    # ------------------------------------------------------------------

    def _select_proofs(self, amount_needed: int) -> tuple[str, list[dict]]:
        """
        Select proofs from the wallet that cover the required amount.
        Returns (serialized token for header, selected proofs).
        """
        selected_proofs = []
        selected_total = 0

        for token_str in self._tokens:
            data = json.loads(base64.urlsafe_b64decode(token_str))
            for proof in data.get("proofs", []):
                if selected_total >= amount_needed:
                    break
                selected_proofs.append(proof)
                selected_total += proof["amount"]
            if selected_total >= amount_needed:
                break

        if selected_total < amount_needed:
            raise InsufficientEcashError(
                f"Need {amount_needed} sats but wallet only has {self._balance_sats}"
            )

        # Build the X-Cashu token with just the selected proofs
        mint_url = json.loads(base64.urlsafe_b64decode(self._tokens[0])).get("mint", "")
        token_data = {"mint": mint_url, "proofs": selected_proofs}
        xcashu_token = base64.urlsafe_b64encode(json.dumps(token_data).encode()).decode()

        return xcashu_token, selected_proofs

    def _remove_spent_proofs(self, spent_proofs: list[dict]) -> None:
        """Remove spent proofs from the wallet."""
        spent_secrets = {p["secret"] for p in spent_proofs}
        new_tokens = []

        for token_str in self._tokens:
            data = json.loads(base64.urlsafe_b64decode(token_str))
            remaining = [p for p in data.get("proofs", []) if p["secret"] not in spent_secrets]
            if remaining:
                data["proofs"] = remaining
                new_tokens.append(
                    base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
                )

        self._tokens = new_tokens
        self._balance_sats = sum(
            p["amount"]
            for t in self._tokens
            for p in json.loads(base64.urlsafe_b64decode(t)).get("proofs", [])
        )

    async def pay_and_fetch(
        self,
        url: str,
        method: str = "GET",
        amount_hint: Optional[int] = None,
        **httpx_kwargs,
    ) -> httpx.Response:
        """
        The magic method. Fetch a URL, paying with ecash if needed.

        1. Try the request
        2. If 402 → extract required amount → select proofs → set X-Cashu header → retry
        3. If change comes back in X-Cashu-Change → add to wallet
        4. Return the response
        """
        headers = httpx_kwargs.pop("headers", {})

        # First try
        resp = await self._http.request(method, url, headers=headers, **httpx_kwargs)

        if resp.status_code != 402:
            return resp

        # Got 402 — need to pay
        try:
            body = resp.json()
            required = body.get("required_amount", amount_hint or 1)
        except Exception:
            required = amount_hint or 1

        # Select proofs and build X-Cashu header
        xcashu_token, spent_proofs = self._select_proofs(required)
        headers["X-Cashu"] = xcashu_token

        # Retry with payment
        resp = await self._http.request(method, url, headers=headers, **httpx_kwargs)

        # Remove spent proofs from wallet
        self._remove_spent_proofs(spent_proofs)

        # Collect change if any
        change_header = resp.headers.get("X-Cashu-Change")
        if change_header:
            self._tokens.append(change_header)
            change_data = json.loads(base64.urlsafe_b64decode(change_header))
            change_amount = sum(p["amount"] for p in change_data.get("proofs", []))
            self._balance_sats += change_amount

        return resp

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def balance(self) -> int:
        """Current ecash balance in sats."""
        return self._balance_sats

    @property
    def num_tokens(self) -> int:
        return len(self._tokens)

    async def status(self) -> dict:
        """Get full agent summary from OpenBalance."""
        self._require_registered()
        resp = await self._http.get(f"{self.api_base}/agents/{self.agent_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Token transfer (agent → agent)
    # ------------------------------------------------------------------

    async def transfer(
        self,
        to_agent_id: str,
        amount_sats: int,
    ) -> dict:
        """Transfer ecash to another agent."""
        self._require_registered()
        xcashu_token, spent_proofs = self._select_proofs(amount_sats)

        resp = await self._http.post(
            f"{self.api_base}/agents/{self.agent_id}/transfer",
            json={"to_agent_id": to_agent_id, "token": xcashu_token},
        )
        resp.raise_for_status()
        self._remove_spent_proofs(spent_proofs)
        return resp.json()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_registered(self):
        if not self.agent_id:
            raise RuntimeError("Agent not registered. Call `await client.register('name')` first.")


class InsufficientEcashError(Exception):
    pass
