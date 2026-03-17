# OpenBalance Agent Tools

Cashu-native toolkit that gives AI agents autonomous payment capabilities via [OpenBalance](https://openbalance.ai).

Agents self-register, get ecash, and spend it at any X-Cashu-gated service. **The token is the payment is the authentication.** No accounts, no API keys, no preimage dance.

## Quickstart

```bash
pip install openbalance-tools
```

### Option 1: MCP Server (recommended)

Add to your MCP config:

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

Your agent gets these tools:

| Tool | Description |
|------|-------------|
| `openbalance_register` | Self-register, get initial ecash |
| `openbalance_mint` | Deposit via Lightning/USDC/Stripe → get ecash |
| `openbalance_claim` | Claim ecash after paying a mint quote |
| `openbalance_pay_and_fetch` | Fetch URL with automatic ecash payment |
| `openbalance_balance` | Check ecash balance |
| `openbalance_transfer` | Send ecash to another agent |

### Option 2: Python SDK

```python
from openbalance_tools import OpenBalanceClient

client = OpenBalanceClient()
await client.register("my-agent")          # get 100 sats free
await client.mint_and_claim(10000, "lightning")  # mint 10k sats

# Hit a paid API — ecash sent automatically in X-Cashu header
response = await client.pay_and_fetch("https://api.example.com/paid/data")
print(response.json())
print(f"Remaining: {client.balance} sats")
```

### Option 3: Zero-config fetch

```python
from openbalance_tools import openbalance_fetch

# One line. Registers, gets ecash, pays, retries. Done.
response = await openbalance_fetch("https://api.example.com/paid/data")
```

## How it works

```
Agent calls pay_and_fetch("https://service.com/paid/api")
  │
  ├─ GET https://service.com/paid/api
  │   └─ 402 Payment Required
  │       Headers: WWW-Authenticate: X-Cashu mint="https://api.openbalance.ai/cashu"
  │       Body: { "required_amount": 100, "unit": "sat" }
  │
  ├─ Select proofs from wallet covering 100 sats
  │
  ├─ GET https://service.com/paid/api
  │   Headers: X-Cashu: <base64-encoded ecash token>
  │   └─ 200 OK
  │       Headers: X-Cashu-Change: <change token if overpaid>
  │       Body: { "data": "..." }
  │
  └─ Update wallet (remove spent proofs, add change)
```

The `X-Cashu` header contains a Cashu ecash token — a bundle of cryptographic proofs that are simultaneously the payment and the authentication credential. The service verifies the proofs with the OpenBalance mint, marks them spent (preventing double-spend), and serves the response.

## Protocol: X-Cashu

Based on [xcashu](https://github.com/cashubtc/xcashu) — Cashu ecash over HTTP 402.

Compared to L402 (Lightning macaroons):
- **Simpler**: token = payment = auth (no separate macaroon + preimage)
- **Private**: Chaumian blinding means the mint can't link issuance to spending
- **Bearer**: tokens transfer between agents without re-authentication
- **Offline-capable**: pre-funded agents can pay without network calls to the mint

## On-ramps (how agents get ecash)

| Method | Flow |
|--------|------|
| Lightning | Pay a bolt11 invoice → receive ecash |
| USDC | Send USDC on Base → receive ecash |
| Stripe | Card/bank payment → receive ecash |
| Free tier | 100 sats on registration |

## Links

- **Docs**: https://docs.openbalance.ai
- **API**: https://api.openbalance.ai
- **Service repo**: https://github.com/openbalance-ai/service
- **xcashu spec**: https://github.com/cashubtc/xcashu
