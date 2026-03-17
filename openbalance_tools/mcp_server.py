"""
OpenBalance MCP Server — Clearing & Settlement for AI Agents.

Exposes the OpenBalance clearing house as MCP tools any agent
framework can use. OpenBalance is the DTCC for the agent economy —
we don't process payments, we clear and settle them.

Run:  python -m openbalance_tools

MCP config:
    {
      "mcpServers": {
        "openbalance": {
          "command": "python",
          "args": ["-m", "openbalance_tools"]
        }
      }
    }

Agent gets: register, deposit, pay_and_fetch, balance, transfer.
Token = payment = auth. Clearing + settlement is automatic.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from .client import OpenBalanceClient


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "openbalance_register",
        "description": (
            "Become a participant in the OpenBalance clearing house. "
            "Returns an agent_id and initial ecash tokens. Call once on first use. "
            "OpenBalance is the DTCC for agents — clears and settles transactions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name"},
                "tier": {
                    "type": "string",
                    "enum": ["free", "pro", "enterprise"],
                    "default": "free",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "openbalance_mint",
        "description": (
            "Deposit funds into the OpenBalance depository via any funding connector. "
            "The clearing house doesn't process payments — connectors handle that. "
            "Crypto: lightning, onchain_btc, usdc_base, usdc_eth, usdc_sol, cashu_token. "
            "Card/wallet: card, apple_pay, google_pay, cash_app, paypal. "
            "Bank/enterprise: ach, sepa, wire, invoice. "
            "Returns connector-specific payment details. "
            "Call openbalance_claim after the connector confirms payment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount_sats": {"type": "integer", "description": "Amount in sats to mint"},
                "on_ramp": {
                    "type": "string",
                    "enum": [
                        "lightning", "onchain_btc",
                        "usdc_base", "usdc_eth", "usdc_sol", "cashu_token",
                        "card", "apple_pay", "google_pay", "cash_app", "paypal",
                        "ach", "sepa", "wire", "invoice"
                    ],
                    "default": "lightning",
                    "description": (
                        "Funding method. Crypto-native: lightning, onchain_btc, "
                        "usdc_base/eth/sol, cashu_token. Fiat: card, apple_pay, "
                        "google_pay, cash_app, paypal. Bank: ach, sepa, wire, invoice."
                    ),
                },
            },
            "required": ["amount_sats"],
        },
    },
    {
        "name": "openbalance_claim",
        "description": "Claim depository receipt (ecash) after funding connector confirms payment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "quote_id": {"type": "string", "description": "The quote ID from openbalance_mint"},
            },
            "required": ["quote_id"],
        },
    },
    {
        "name": "openbalance_pay_and_fetch",
        "description": (
            "Fetch a URL with automatic clearing and settlement. If the "
            "service returns 402, the clearing house verifies your ecash "
            "proofs and settles the transaction. Returns the response. "
            "This is the simplest way to access paid APIs — use this "
            "instead of regular HTTP requests for any service that might charge."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "openbalance_balance",
        "description": "Check your ecash wallet balance in sats.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "openbalance_transfer",
        "description": "Book-entry transfer of ecash to another participant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to_agent_id": {"type": "string"},
                "amount_sats": {"type": "integer"},
            },
            "required": ["to_agent_id", "amount_sats"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

_client: OpenBalanceClient | None = None


def _get_client() -> OpenBalanceClient:
    global _client
    if _client is None:
        api_base = os.getenv("OPENBALANCE_API", "https://api.openbalance.ai/v1")
        _client = OpenBalanceClient(api_base=api_base)
    return _client


async def handle_tool(name: str, arguments: dict[str, Any]) -> dict:
    client = _get_client()

    if name == "openbalance_register":
        return await client.register(
            name=arguments["name"],
            tier=arguments.get("tier", "free"),
        )

    elif name == "openbalance_mint":
        return await client.mint(
            amount_sats=arguments["amount_sats"],
            on_ramp=arguments.get("on_ramp", "lightning"),
        )

    elif name == "openbalance_claim":
        return await client.claim(quote_id=arguments["quote_id"])

    elif name == "openbalance_pay_and_fetch":
        resp = await client.pay_and_fetch(
            url=arguments["url"],
            method=arguments.get("method", "GET"),
        )
        return {
            "status_code": resp.status_code,
            "body": resp.text[:10000],
            "ecash_remaining": client.balance,
        }

    elif name == "openbalance_balance":
        return {
            "balance_sats": client.balance,
            "num_tokens": client.num_tokens,
            "agent_id": client.agent_id,
        }

    elif name == "openbalance_transfer":
        return await client.transfer(
            to_agent_id=arguments["to_agent_id"],
            amount_sats=arguments["amount_sats"],
        )

    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# MCP stdio server
# ---------------------------------------------------------------------------

async def handle_message(msg: dict) -> dict | None:
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "openbalance", "version": "0.3.0"},
            },
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    elif method == "tools/call":
        params = msg.get("params", {})
        try:
            result = await handle_tool(params.get("name", ""), params.get("arguments", {}))
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True},
            }

    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


async def serve():
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            msg = json.loads(line.decode())
        except json.JSONDecodeError:
            continue
        response = await handle_message(msg)
        if response:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
