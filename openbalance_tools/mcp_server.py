"""
OpenBalance MCP Server

An MCP (Model Context Protocol) server that exposes OpenBalance
capabilities as tools any MCP-compatible agent can use.

Run standalone:
    python -m openbalance_tools.mcp_server

Or add to your MCP config (claude_desktop_config.json, etc.):
    {
      "mcpServers": {
        "openbalance": {
          "command": "python",
          "args": ["-m", "openbalance_tools.mcp_server"],
          "env": {
            "OPENBALANCE_API": "https://api.openbalance.ai/v1"
          }
        }
      }
    }

This gives any Claude, LangChain, CrewAI, or other MCP-compatible
agent native payment capabilities with zero custom integration.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from .client import OpenBalanceClient


# ---------------------------------------------------------------------------
# Tool definitions (MCP schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "openbalance_register",
        "description": (
            "Register this agent with OpenBalance to get payment capabilities. "
            "Call this once before using any other OpenBalance tools. "
            "Returns an agent_id and wallet information."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A name for this agent (e.g. 'research-agent-v2')",
                },
                "description": {
                    "type": "string",
                    "description": "What this agent does",
                    "default": "",
                },
                "tier": {
                    "type": "string",
                    "enum": ["free", "pro", "enterprise"],
                    "description": "Subscription tier. Free: Lightning only, 10 txns/day. Pro: all rails, 1000 txns/day.",
                    "default": "free",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "openbalance_acquire",
        "description": (
            "Pay for and acquire access to a paid API or service. "
            "OpenBalance automatically discovers the service's payment requirements, "
            "selects the cheapest payment rail (Lightning, USDC, or Stripe), "
            "funds your wallet if needed, and returns an authentication token. "
            "Use this when you hit a 402 Payment Required response, or proactively "
            "before calling a service you know is paid."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_url": {
                    "type": "string",
                    "description": "The URL of the paid service to access",
                },
                "preferred_rail": {
                    "type": "string",
                    "enum": ["lightning", "usdc", "stripe"],
                    "description": "Optional: prefer a specific payment rail",
                },
                "auto_fund": {
                    "type": "boolean",
                    "description": "Automatically fund the wallet if balance is low (default: true)",
                    "default": True,
                },
            },
            "required": ["service_url"],
        },
    },
    {
        "name": "openbalance_fund",
        "description": (
            "Add funds to your OpenBalance wallet on a specific payment rail. "
            "Use this to pre-fund your wallet before making payments, or to "
            "top up when running low."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rail": {
                    "type": "string",
                    "enum": ["lightning", "usdc", "stripe"],
                    "description": "Which payment rail to fund",
                },
                "amount_usd": {
                    "type": "number",
                    "description": "Amount in USD to add",
                },
            },
            "required": ["rail", "amount_usd"],
        },
    },
    {
        "name": "openbalance_status",
        "description": (
            "Check your OpenBalance wallet balances, active entitlements, "
            "and recent transactions. Use this to understand your current "
            "spending state before making decisions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "openbalance_delegate",
        "description": (
            "Delegate access to a paid service to another agent with "
            "restricted scopes. The child agent receives a narrower "
            "entitlement without paying again."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "child_agent_id": {
                    "type": "string",
                    "description": "The agent_id of the agent to delegate to",
                },
                "service_url": {
                    "type": "string",
                    "description": "The service URL to delegate access for",
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restricted scopes for the child (e.g. ['read'])",
                },
            },
            "required": ["child_agent_id", "service_url"],
        },
    },
    {
        "name": "openbalance_fetch",
        "description": (
            "Fetch a URL with automatic payment handling. If the service "
            "returns 402 Payment Required, OpenBalance pays for access "
            "and retries. Returns the response body. This is the simplest "
            "way to access paid APIs — just use this instead of a regular "
            "HTTP request."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                },
            },
            "required": ["url"],
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
    """Execute an OpenBalance tool and return the result."""
    client = _get_client()

    if name == "openbalance_register":
        result = await client.register(
            name=arguments["name"],
            description=arguments.get("description", ""),
            tier=arguments.get("tier", "free"),
        )
        return result

    elif name == "openbalance_acquire":
        result = await client.acquire(
            service_url=arguments["service_url"],
            preferred_rail=arguments.get("preferred_rail"),
            auto_fund=arguments.get("auto_fund", True),
        )
        return result

    elif name == "openbalance_fund":
        result = await client.fund(
            rail=arguments["rail"],
            amount_usd=arguments["amount_usd"],
        )
        return result

    elif name == "openbalance_status":
        result = await client.status()
        return result

    elif name == "openbalance_delegate":
        result = await client.delegate(
            child_agent_id=arguments["child_agent_id"],
            service_url=arguments["service_url"],
            scopes=arguments.get("scopes"),
        )
        return result

    elif name == "openbalance_fetch":
        from .middleware import openbalance_fetch
        resp = await openbalance_fetch(
            url=arguments["url"],
            method=arguments.get("method", "GET"),
            agent_name=client.agent_name or "mcp-agent",
        )
        return {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp.text[:10000],  # cap response size
        }

    else:
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# MCP stdio server (JSON-RPC over stdin/stdout)
# ---------------------------------------------------------------------------

async def handle_message(msg: dict) -> dict | None:
    """Handle a single JSON-RPC message."""
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "openbalance",
                    "version": "0.1.0",
                },
            },
        }

    elif method == "notifications/initialized":
        return None  # no response for notifications

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            result = await handle_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, default=str),
                        }
                    ],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }


async def serve():
    """Run the MCP server over stdio."""
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
        if response is not None:
            out = json.dumps(response) + "\n"
            sys.stdout.write(out)
            sys.stdout.flush()


def main():
    """Entry point for `python -m openbalance_tools.mcp_server`."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
