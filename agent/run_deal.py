"""The agent: buy the answer, then put it in front of the court.

This is the whole loop in one command, and it is what the skill wraps:

    python agent/run_deal.py --quality good     # the seller is honest
    python agent/run_deal.py --quality bad      # the seller lies, the court refunds

What it does, in order:

1. asks the seller's x402 route for a report, paying $0.01 USDC on Base
   Sepolia with a real EIP-3009 authorization;
2. keeps the receipt (`/evidence/<deal>`), which is the exact bytes the
   payment bought;
3. opens a GenLayer deal that freezes where the answer must live, which field
   it must carry, and how far it may drift from two independent feeds;
4. asks the court to rule, and prints who keeps the escrow.
"""

import argparse
import base64
import json
import os
import subprocess
import sys

import requests
from eth_account import Account
from x402.client import PaymentPayloadV1, x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.mechanisms.evm.signers import EthAccountSigner

HERE = os.path.dirname(os.path.abspath(__file__))
SELLER = os.environ.get("SELLER_URL", "http://127.0.0.1:8402")
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"

# what the buyer will accept: the field, and how far it may drift from the feeds
MANDATE = {
    "field": "price",
    "tolerance_bps": 50,          # 0.5%
    "escrow_wei": str(10 ** 17),  # 0.1 GEN
}


def load_key() -> str:
    path = os.path.join(HERE, "wallet.json")
    if not os.path.exists(path):
        raise SystemExit("run `python agent/make_wallet.py` first")
    return json.load(open(path))["private_key"]


def buy_report(quality: str) -> dict:
    """Pay the seller over x402 and return the report it delivers."""
    url = f"{SELLER}/report?quality={quality}"
    key = load_key()
    signer = EthAccountSigner(key)
    client = x402ClientSync()
    client.register("eip155:*", ExactEvmScheme(signer=signer))

    first = requests.get(url, timeout=30)
    if first.status_code != 402:
        raise RuntimeError(f"expected a 402, got {first.status_code}")
    required = json.loads(base64.b64decode(first.headers[PAYMENT_REQUIRED_HEADER]))
    print("  402 payment required:",
          required["accepts"][0]["maxAmountRequired"], "units of",
          required["accepts"][0]["asset"][:10] + "...",
          "on", required["accepts"][0]["network"])

    payload = client.create_payment_payload(required)
    payload_json = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload
    signed = base64.b64encode(json.dumps(payload_json).encode()).decode()

    paid = requests.get(url, timeout=30, headers={PAYMENT_SIGNATURE_HEADER: signed})
    if paid.status_code != 200:
        raise RuntimeError(f"payment rejected: {paid.status_code} {paid.text[:200]}")
    settlement = paid.headers.get(PAYMENT_RESPONSE_HEADER, "")
    print("  paid and settled:", json.loads(base64.b64decode(settlement))["transaction"][:22] + "...")
    return paid.json()


def receipt_for(report_body: dict) -> dict:
    """The free receipt: the exact bytes the payment bought."""
    deal = report_body.get("deal")
    r = requests.get(f"{SELLER}/evidence/{deal}", timeout=30)
    r.raise_for_status()
    return r.json()


def genlayer(*args: str) -> str:
    """Talk to the deployed court through the thin node helper."""
    node_helper = os.path.join(HERE, "genlayer.mjs")
    out = subprocess.run(["node", node_helper, *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-600:])
    return out.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", choices=["good", "bad"], default="good")
    ap.add_argument("--skip-payment", action="store_true",
                    help="read a receipt the seller already produced")
    ap.add_argument("--receipt", help="deal id of an existing receipt")
    args = ap.parse_args()

    print(f"[1/4] asking the seller for a {args.quality} answer")
    if args.skip_payment and args.receipt:
        body = {"deal": args.receipt}
    else:
        body = buy_report(args.quality)
    print("      report:", json.dumps(body))

    print("[2/4] fetching the receipt the court will read")
    receipt = receipt_for(body)
    print("      receipt:", json.dumps(receipt))

    print("[3/4] opening a GenLayer deal that freezes the terms")
    seller_address = os.environ.get("SELLER_ADDRESS", "0x15B7a1BBadbf50e25245A4f2B9A8c69B8EEe04b7")
    deal_id = genlayer(
        "open", seller_address, SELLER + "/evidence/" + body["deal"], MANDATE["field"],
        str(MANDATE["tolerance_bps"]), MANDATE["escrow_wei"],
    )
    print("      deal:", deal_id)

    print("[4/4] asking the court to rule")
    verdict = genlayer("settle", deal_id)
    print("      verdict:", verdict)
    print()
    if '"SETTLED"' in verdict or verdict.strip() == "SETTLED":
        print("the seller keeps the escrow: the answer held up")
    else:
        print("the buyer keeps the escrow: the answer did not hold up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
