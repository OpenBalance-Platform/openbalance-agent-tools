# OpenBalance Agent Tools

Open-source toolkit that gives AI agents autonomous payment capabilities via [OpenBalance](https://openbalance.ai).

Agents self-register, get a wallet, and pay for any L402/x402/Stripe-gated service — no human signup required.

## Quickstart

```bash
pip install openbalance-tools
```

### Option 1: MCP Server (recommended)

Add to your MCP config (`claude_desktop_config.json`, `.mcp.json`, etc.):

```json
{
  "mcpServers": {
    "openbalance": {
      "command": "python",
      "args": ["-m", "openbalance_tools"]
    }
  }
}
```

Your agent now has these tools:

| Tool | Description |
|------|-------------|
| `openbalance_register` | Self-register and get a wallet |
| `openbalance_acquire` | Pay for and access any paid service |
| `openbalance_fund` | Top up wallet balance |
| `openbalance_status` | Check balances and spending |
| `openbalance_delegate` | Share scoped access with sub-agents |
| `openbalance_fetch` | Drop-in HTTP fetch with auto-payment |

### Option 2: Python SDK

```python
from openbalance_tools import OpenBalanceClient

client = OpenBalanceClient()
await client.register("my-research-agent")
await client.fund("lightning", 10.00)

# Acquire access to a paid API
ent = await client.acquire("https://api.example.com/v1/data")
headers = client.auth_headers(ent)
# Use headers in your HTTP requests
```

### Option 3: Zero-config fetch

```python
from openbalance_tools import openbalance_fetch

# One line. Handles 402 detection, registration, payment, retry.
response = await openbalance_fetch(
    "https://api.premium-data.example/v1/prices",
    agent_name="my-agent",
)
print(response.json())
```

## How it works

1. Agent hits a paid service → gets HTTP 402 Payment Required
2. OpenBalance discovers which rails the service accepts (Lightning/L402, USDC/x402, Stripe)
3. Router picks the cheapest funded rail
4. If wallet is empty, auto-funds from fiat via Strike (Lightning) or MoonPay (USDC)
5. Pays and returns an auth token (macaroon, receipt, or session)
6. Agent retries the request with the token → gets the data

## Supported payment protocols

- **L402** — Lightning Network (via Strike). Sub-cent micropayments, ~1.5s settlement.
- **x402** — USDC on Base (via Coinbase). Stablecoin payments, ~2s settlement.
- **Stripe** — Traditional card payments (fallback). Universal acceptance, higher fees.

## Agent tiers

| Tier | Rails | Txns/day | Max payment |
|------|-------|----------|-------------|
| Free | Lightning only | 10 | ~$3.30 |
| Pro | All | 1,000 | ~$333 |
| Enterprise | All | 100,000 | Custom |

## Links

- **API docs**: https://docs.openbalance.ai
- **Dashboard**: https://openbalance.ai/dashboard
- **Service repo**: https://github.com/openbalance-ai/service
- **This repo**: https://github.com/openbalance-ai/agent-tools
