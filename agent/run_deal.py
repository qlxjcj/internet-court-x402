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
import time

import requests
from eth_account import Account
from x402.client import PaymentPayloadV1, PaymentRequiredV1, x402ClientSync
from x402.mechanisms.evm.exact import register_exact_evm_client
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
    signer = EthAccountSigner(Account.from_key(key))
    client = register_exact_evm_client(x402ClientSync(), signer)

    first = requests.get(url, timeout=30)
    if first.status_code != 402:
        raise RuntimeError(f"expected a 402, got {first.status_code}")
    required_raw = json.loads(base64.b64decode(first.headers[PAYMENT_REQUIRED_HEADER]))
    required = PaymentRequiredV1.model_validate(required_raw)
    print("  402 payment required:",
          required_raw["accepts"][0]["maxAmountRequired"], "units of",
          required_raw["accepts"][0]["asset"][:10] + "...",
          "on", required_raw["accepts"][0]["network"])

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
    """The free receipt: the exact bytes the payment bought.

    It has to live somewhere the validators can reach - a court that cannot read
    the evidence cannot rule on it - so it is published with the repository and
    the deal points at its raw URL.
    """
    deal = report_body.get("deal")
    r = requests.get(f"{SELLER}/evidence/{deal}", timeout=30)
    r.raise_for_status()
    return r.json()


REPO_RAW = "https://raw.githubusercontent.com/qlxjcj/internet-court-x402/master/evidence"


def publish_receipt(receipt: dict) -> str:
    """Commit the receipt so the court can fetch it from a public URL."""
    deal = receipt["deal"]
    folder = os.path.join(HERE, "..", "evidence")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{deal}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    subprocess.run(["git", "add", path], cwd=os.path.join(HERE, ".."), check=True, capture_output=True)
    subprocess.run(["git", "-c", "core.safecrlf=false", "commit", "-q", "-m", f"receipt {deal}"],
                   cwd=os.path.join(HERE, ".."), check=True, capture_output=True)
    for _ in range(5):
        p = subprocess.run(["git", "push", "origin", "HEAD"],
                           cwd=os.path.join(HERE, ".."), capture_output=True, text=True)
        if p.returncode == 0:
            break
        time.sleep(4)
    return f"{REPO_RAW}/{deal}.json"


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
    public_url = publish_receipt(receipt)
    print("      published:", public_url)

    print("[3/4] opening a GenLayer deal that freezes the terms")
    seller_address = os.environ.get("SELLER_ADDRESS", "0x15B7a1BBadbf50e25245A4f2B9A8c69B8EEe04b7")
    deal_id = genlayer(
        "open", seller_address, public_url, MANDATE["field"],
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
