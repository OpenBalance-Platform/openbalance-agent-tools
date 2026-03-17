# OpenBalance Agent Tools

Participant SDK for the [OpenBalance](https://openbalance.ai) clearing house — the DTCC for the agent economy.

Agents become participants, receive ecash from the depository, and spend it at any X-Cashu-gated service. **The clearing house verifies proofs, settles transactions, and issues change. We don't process payments — we clear and settle them.**

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
| `openbalance_register` | Become a clearing house participant, get initial ecash |
| `openbalance_mint` | Deposit via any funding connector → get ecash |
| `openbalance_claim` | Claim depository receipt after deposit confirmed |
| `openbalance_pay_and_fetch` | Fetch URL with automatic clearing + settlement |
| `openbalance_balance` | Check ecash balance |
| `openbalance_transfer` | Book-entry transfer to another participant |

### Option 2: Python SDK

```python
from openbalance_tools import OpenBalanceClient

client = OpenBalanceClient()
await client.register("my-agent")               # become a participant
await client.mint_and_claim(10000, "lightning")  # deposit 10k sats

# Hit a paid API — clearing + settlement handled automatically
response = await client.pay_and_fetch("https://api.example.com/paid/data")
print(response.json())
print(f"Remaining: {client.balance} sats")
```

### Option 3: Zero-config fetch

```python
from openbalance_tools import openbalance_fetch

# One line. Registers, deposits, clears, settles. Done.
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
  │   │
  │   │  Clearing house: verify proofs → mark spent → settle
  │   │
  │   └─ 200 OK
  │       Headers: X-Cashu-Change: <change token if overpaid>
  │       Body: { "data": "..." }
  │
  └─ Update wallet (remove spent proofs, add change)
```

The `X-Cashu` header contains a Cashu ecash token — a bundle of cryptographic proofs that are simultaneously the payment and the authentication credential. The clearing house verifies the proofs are authentic and unspent (clearing), marks them consumed (settlement), and issues change if overpaid. The service gets paid without ever touching a payment processor.

## The DTCC model

OpenBalance is not a payment processor. It's the clearing and settlement layer:

| DTCC Function | OpenBalance |
|---|---|
| Depository | Cashu mint — issues ecash, custodies signing keys |
| Clearing | Verify proofs are authentic and unspent |
| Settlement | Mark proofs consumed, record transaction |
| Book-entry | Participant-to-participant token transfers |
| Membership | Agent registry, tiers, entitlements |

Funding connectors (Lightning, USDC, Stripe, etc.) are pluggable deposit adapters. They bring money into the depository but are not OpenBalance's core business.

## Funding connectors (how participants deposit)

| Connector | Type | Speed |
|---|---|---|
| Lightning | Crypto | Instant |
| On-chain BTC | Crypto | 10-60 min |
| USDC (Base/ETH/Solana) | Crypto | < 5 min |
| Cashu cross-mint | Crypto | Instant |
| Credit/debit card | Fiat | Instant |
| Apple Pay / Google Pay | Fiat | Instant |
| Cash App / PayPal | Fiat | Instant |
| ACH / SEPA | Bank | 1-3 days |
| Wire transfer | Bank | Same day |
| Net-30 invoice | Enterprise | Pre-approved |

## Links

- **Docs**: https://docs.openbalance.ai
- **API**: https://api.openbalance.ai
- **Service repo**: https://github.com/openbalance-ai/service
- **X-Cashu spec**: https://github.com/cashubtc/xcashu
