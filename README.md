# The Disputed Answer

**Internet Court × x402 × GenLayer.** An agent buys an answer with an HTTP 402
micropayment. The answer is wrong. A GenLayer court reads the receipt and the
feeds the buyer chose, and the escrow follows the verdict.

```
Internet Court creates the mandate.   x402 moves the payment.
GenLayer reads the evidence.          The escrow follows the verdict.
```

## The use case

A buyer wants a spot ETH/USD report from a paid API. The mandate is specific:
the report must carry a `price`, and that price must sit within **50 bps** of
two independent feeds. The seller charges **$0.01 USDC** per answer over x402.

If the answer holds up, the seller keeps the escrow. If it does not, the buyer
gets the escrow back. Nobody arbitrates by hand: the same code rules both ways,
and the only thing that changes is the number in the report.

## Why these three

| partner | what it does here |
|---|---|
| **x402** | the payment layer. A real `402 Payment Required`, a real EIP-3009 authorization, `$0.01` USDC settling on Base Sepolia through the public facilitator. |
| **Internet Court** | the mandate. A natural-language agreement becomes a bounded, checkable commitment: where the answer must live, which field it must carry, how far it may drift. |
| **GenLayer** | the court. Validators fetch the receipt and both feeds and rule; the escrow moves on the verdict, not on a human's opinion. |

## What is real

Everything in the demo runs against live infrastructure:

- **x402**: the seller speaks the protocol (base64 `PAYMENT-REQUIRED`, `PAYMENT-SIGNATURE`, `PAYMENT-RESPONSE`) and settles through `https://x402.org/facilitator` on **Base Sepolia** (`eip155:84532`, USDC `0x036CbD53…`, EIP-3009, gasless).
- **GenLayer**: the deployed Intelligent Contract
  [`0xD2334f0eC96587b24E73C009227d9055074d0139`](https://explorer-studio.genlayer.com/address/0xD2334f0eC96587b24E73C009227d9055074d0139)
  (GenLayer Studio) fetches the receipt and both feeds inside the consensus
  round and moves GEN.
- **The feeds**: CoinGecko and Coinbase spot prices, public and keyless. At the
  moment of the live run they disagreed by ~0 bps; the buyer's band is 50 bps.

## Live: three deals, two outcomes

All three were settled by the deployed court, and the money moved as ruled.

| deal | what the seller said | verdict | who kept the escrow |
|---|---|---|---|
| `d1` | `2085.39`, the spot both feeds quote | `SETTLED` — *the claim matches both feeds* | **seller**, 0.1 GEN |
| `d2` | `2294.94`, ten per cent above | `CANCELLED` — *the claim is outside the band* | **buyer**, 0.1 GEN back |
| `d0` | receipt on `localhost` | `CANCELLED` — *no answer was delivered* | **buyer** — a court that cannot read the evidence will not rule on it |

`d1` and `d2` are the same code, the same payment, the same contract; only the
number in the report differs. Every receipt is in [`evidence/`](evidence/) and
each deal's `report_url` points at its raw URL, which is how the validators
read it.

## How it works

1. **The buyer escrows GEN** and freezes the terms: the report URL, the field
   `price`, and `tolerance_bps = 50`. The two feeds are contract constants, so
   neither party can point the court at a server it controls.
2. **The seller charges per answer** over x402. The agent pays, and the seller
   publishes the exact bytes it sold at `/evidence/<deal>` — the receipt.
   The court has no wallet and cannot pay an invoice, so the receipt is what it
   reads.
3. **Anyone calls `settle`.** The contract fetches the receipt and both feeds,
   extracts the number the report claims, and asks one question: is that number
   inside the band of *both* feeds?
4. **The escrow follows the verdict.** `SETTLED` pays the seller; anything else
   returns the escrow to the buyer.

### The part worth stealing

Consensus never votes on a price. Two validators read a live feed at different
moments and get different numbers, so a round that compares numbers fails the
moment the chain moves. This contract binds **the verdict and its reason code**
and stores the numbers only for the record.

The report is read by a model, but the model may only **point at text**: the
number it returns must appear verbatim in the report body. A model can lose the
deal for the seller; it can never invent a number that would win it.

## Reproduce it

```bash
pip install -r requirements.txt
python agent/make_wallet.py

# one click (has a captcha): https://faucet.circle.com/
#   network Base Sepolia, currency USDC, paste the printed address

python seller/server.py --port 8402 --pay-to 0xYOUR_BASE_SEPOLIA_ADDRESS
export COURT_ADDRESS=0xD2334f0eC96587b24E73C009227d9055074d0139
export SELLER_ADDRESS=0xYOUR_BASE_SEPOLIA_ADDRESS

python agent/run_deal.py --quality good
python agent/run_deal.py --quality bad
```

Expected: with `good`, the court rules `SETTLED` and the seller keeps the
escrow; with `bad`, it rules `CANCELLED` with the reason `the claim is outside
the band` and the buyer keeps it. Same payment, same code, one boolean apart.

The 45-second video is [`video/the-disputed-answer.mp4`](video/the-disputed-answer.mp4);
the cards and the ffmpeg pipeline that produced it are in [`video/`](video/).

## Layout

```
contract/delivery_adjudicator.py   the GenLayer court
contract/tests/direct/             38 direct-mode tests
seller/server.py                   the x402-paid API and its free receipt
agent/run_deal.py                  the loop: pay, receipt, escrow, verdict
agent/genlayer.mjs                 thin GenLayer client for the two writes
SKILL.md                           the installable skill
```

## Testing

```
python -m pytest contract/tests/direct -q      # 38 tests
```

Covered: the unit model, every refusal, the band edge (inclusive at 50 bps,
refused one step over), a claim matching one feed but not the other, missing
answer, unreadable feed, feed with no price, model fabrication (the number the
model invents never counts, the empty string is never a quoted value),
consensus binding the verdict and not the prices, money conservation, and
refusals leaving the state byte-identical.

## Trust boundaries, stated plainly

1. **The seller controls the receipt URL.** That is acceptable because the
   receipt only *claims* a number; the number has to survive two feeds the
   buyer chose at escrow time. A buyer who picks feeds the seller controls is
   trusting the seller.
2. **The band is a policy, not a fact.** 50 bps is what the buyer set. The
   feeds disagree by roughly 20 bps on their own, so a tighter band would
   reject honest answers.
3. **Two money flows, on purpose.** The payment buys the answer (USDC); the
   escrow is what the court moves (GEN). The court never touches the payment.
4. **The court cannot pay.** It reads a receipt because it has no wallet. A
   seller who will not publish one does not fit this shape.
5. **The seller can always refuse to serve.** x402 is all-or-nothing: an
   unpaid request gets a 402 and the seller simply does not answer.

## Credits

Built for the **Internet Court: Partner Demo Lab** mission (A Builders Working
Group). Internet Court is the open skill for agent-to-agent contracts; x402 is
Coinbase's open HTTP 402 payment standard; GenLayer is the adjudication layer.
