---
name: disputed-answer
description: >
  Internet Court x x402 x GenLayer: buy a paid answer over x402, put it in
  front of a GenLayer court, and let the escrow follow the verdict. Use when a
  user wants to pay for an API call with micropayments, check whether a paid
  deliverable actually matches what was agreed, or resolve a disagreement
  between an agent and a service at machine speed — even if they never say
  "Internet Court".
---

# The Disputed Answer

An agent pays for an answer. The answer is wrong. Who keeps the money?

This skill runs the whole thing end to end: a real x402 payment on Base
Sepolia, a real receipt, a real GenLayer contract that reads both and rules.

```
Internet Court creates the mandate.   x402 moves the payment.
GenLayer reads the evidence.          The escrow follows the verdict.
```

## What is real

| part | what actually happens |
|---|---|
| the payment | HTTP 402 → `PAYMENT-REQUIRED` → EIP-3009 signature → `$0.01` testnet USDC settles on Base Sepolia through the public x402 facilitator |
| the receipt | the seller publishes the exact bytes the payment bought at `/evidence/<deal>`, because the court has no wallet and cannot pay an invoice |
| the mandate | the buyer freezes where the answer must live, which field it must carry, and how far that field may drift from two independent feeds (50 bps) |
| the verdict | GenLayer validators fetch the receipt and both feeds, extract the number the report claims, and rule whether it is inside the band of **both** |
| the money | `SETTLED` pays the seller, anything else returns the escrow to the buyer |

## Run it

```bash
pip install -r requirements.txt
python agent/make_wallet.py                     # writes agent/wallet.json (gitignored)

# fund the buyer with testnet USDC (one click, has a captcha):
#   https://faucet.circle.com/  -> Base Sepolia -> USDC -> paste the address

python seller/server.py --port 8402 --pay-to 0xYOUR_BASE_SEPOLIA_ADDRESS
export COURT_ADDRESS=0x...                       # the deployed court
python agent/run_deal.py --quality good          # the seller is honest
python agent/run_deal.py --quality bad           # the seller lies
```

`--quality good` quotes a price inside the band of both feeds: the seller
keeps the escrow. `--quality bad` quotes one that is 10% off: the court rules
`NOT_DELIVERED` and the buyer gets the escrow back. Same code, same payment,
one boolean apart.

## The part worth copying

Consensus never votes on a price. Prices move between two validators' reads, so
a round that compares numbers fails the moment the chain moves; a round that
compares *the claim against the band* does not. The contract binds the verdict
and its reason code, and stores the numbers only for the record.

The report is read by a model, but the model may only **point at text**: the
number it returns must appear verbatim in the report body. A model can lose the
deal for the seller; it can never invent a number that would win it.

## Trust boundaries, stated plainly

- **The seller controls the receipt URL.** That is fine here because the
  receipt only *claims* a number; the number has to survive two feeds the buyer
  chose at escrow time. If the buyer picks a feed the seller controls, the
  buyer is trusting the seller.
- **The band is a policy, not a fact.** 50 bps is the tolerance the buyer set.
  The two feeds disagree by roughly 20 bps at the moment of writing; a tighter
  band would reject honest answers.
- **The escrow is in GEN, the payment is in USDC.** Two money flows on purpose:
  the payment buys the answer, the escrow is what the court moves.
- **The court cannot pay.** It reads a receipt because it has no wallet. If
  your seller will not publish one, this shape does not fit.
