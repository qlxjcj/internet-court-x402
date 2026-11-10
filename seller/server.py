"""The seller: an x402-paid answer, with a free receipt for the court.

One route sells the answer (`GET /report`), one route hands the exact same
bytes to anyone who needs to check it (`GET /evidence/<deal>`). The court
cannot pay an x402 invoice - no wallet, no facilitator - so the receipt is the
thing it reads, and the receipt is what the payment bought.

Run it:

    python seller/server.py --port 8402 --pay-to 0xYOUR_BASE_SEPOLIA_ADDRESS

Then the first request is refused with a real HTTP 402, the agent pays $0.01
USDC on Base Sepolia, and the retry gets the report.
"""

import argparse
import base64
import json
import os
import uuid
from types import SimpleNamespace
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from x402.client import PaymentPayloadV1
from x402.http import HTTPFacilitatorClientSync
from x402.server import PaymentRequirementsV1

# Base Sepolia USDC, 6 decimals. Price is $0.01 per answer.
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
PRICE_UNITS = "10000"
NETWORK = "base-sepolia"          # x402 v1 names networks; the SDK matches on this
FACILITATOR = "https://x402.org/facilitator"
ASSET_TRANSFER_METHOD = "eip3009"

PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"

# the honest answer, and the dishonest one
HONEST_PRICE = 2100.0
LIAR_MULTIPLIER = 1.10


app = FastAPI(title="The Paid Answer")
REPORTS: dict[str, dict] = {}
FACILITATOR_CLIENT = HTTPFacilitatorClientSync({"url": FACILITATOR})
PAY_TO = os.environ.get("PAY_TO", "0x0000000000000000000000000000000000000000")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8402")


def live_price() -> float:
    """The spot the feeds are quoting right now.

    The seller reads them too: a fixed number would drift outside the buyer's
    band within minutes and make every honest answer look like a lie. If neither
    feed answers, raise - a made-up price is worse than no answer at all.
    """
    import time
    import urllib.request

    for attempt in range(4):
        for url, path in (
            ("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd", ("ethereum", "usd")),
            ("https://api.coinbase.com/v2/prices/ETH-USD/spot", ("data", "amount")),
        ):
            try:
                with urllib.request.urlopen(url, timeout=15) as r:
                    node = json.loads(r.read().decode())
                for key in path:
                    node = node[key]
                return float(node)
            except Exception:
                continue
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("neither feed is answering")


def build_report(quality: str) -> dict:
    """What the buyer is paying for.

    `good` quotes the spot the feeds are quoting, so it sits inside the band of
    both. `bad` quotes one that is 10% off - the difference between the two is
    the whole dispute.
    """
    spot = live_price()
    price = round(spot, 2) if quality == "good" else round(spot * LIAR_MULTIPLIER, 2)
    return {
        "symbol": "ETH/USD",
        "price": price,
        "window": "24h",
        "quality": quality,
        "note": "spot at report time, rounded to cents",
    }


def requirements_for(url: str) -> PaymentRequirementsV1:
    return PaymentRequirementsV1(
        scheme="exact",
        network=NETWORK,
        maxAmountRequired=PRICE_UNITS,
        resource=url,
        description="One ETH/USD spot report",
        mimeType="application/json",
        payTo=PAY_TO,
        maxTimeoutSeconds=600,
        asset=USDC_BASE_SEPOLIA,
        extra={"assetTransferMethod": ASSET_TRANSFER_METHOD,
               "name": "USDC", "version": "2"},
    )


def b64(obj) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


def call_facilitator(kind: str, payload, requirements, attempts: int = 6):
    """Ask the facilitator, with retries, in the shape it accepts.

    The SDK's facilitator client wraps v1 payloads in a way the public
    facilitator rejects, so this posts the envelope the protocol actually
    documents: `paymentPayload` plus `paymentRequirements`. A facilitator that
    cannot be reached is not a rejection - it is a network hiccup, and treating
    it as one would let the seller keep money for an answer it never verified.
    """
    import time

    import requests

    body = {
        "x402Version": 1,
        "paymentPayload": payload.model_dump(exclude_none=True)
        if hasattr(payload, "model_dump") else payload,
        "paymentRequirements": requirements.model_dump(exclude_none=True)
        if hasattr(requirements, "model_dump") else requirements,
    }
    last = None
    for i in range(attempts):
        try:
            r = requests.post(FACILITATOR + "/" + kind, json=body, timeout=30,
                              headers={"Content-Type": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"{kind} failed ({r.status_code}): {r.text[:200]}")
            data = r.json()
            if kind == "verify":
                return SimpleNamespace(isValid=bool(data.get("isValid")),
                                       invalidReason=data.get("invalidReason"),
                                       invalidMessage=data.get("invalidMessage"))
            return SimpleNamespace(success=bool(data.get("success")),
                                   transaction=data.get("transaction", ""),
                                   network=data.get("network", ""),
                                   amount=data.get("amount"),
                                   payer=data.get("payer"),
                                   errorReason=data.get("errorReason"),
                                   model_dump=lambda **kw: data)
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("facilitator unreachable: " + str(last)[:160])


def unb64(text: str):
    return json.loads(base64.b64decode(text.encode()).decode())


@app.get("/report")
def report(request: Request, quality: str = "good") -> Response:
    """The paid route: a real 402 first, the answer only after a real payment."""
    url = str(request.url)
    requirements = requirements_for(url)

    signed = request.headers.get(PAYMENT_SIGNATURE_HEADER)
    if not signed:
        body = {"x402Version": 1, "accepts": [requirements.model_dump(exclude_none=True)]}
        return JSONResponse(
            status_code=402,
            content=body,
            headers={PAYMENT_REQUIRED_HEADER: b64(body)},
        )

    try:
        raw = unb64(signed)
        payload = PaymentPayloadV1(**raw) if not isinstance(raw, PaymentPayloadV1) else raw
    except Exception:
        return JSONResponse(status_code=402, content={"error": "undecodable payment payload"})

    try:
        verification = call_facilitator("verify", payload, requirements)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "facilitator unreachable",
                                                     "detail": str(e)[:160]})

    if not getattr(verification, "isValid", False):
        detail = {
            "error": "payment rejected",
            "reason": getattr(verification, "invalidReason", None),
            "message": getattr(verification, "invalidMessage", None),
        }
        return JSONResponse(status_code=402, content=detail)

    deal = uuid.uuid4().hex[:12]
    body = build_report(quality)
    body["deal"] = deal
    REPORTS[deal] = body

    try:
        settlement = call_facilitator("settle", payload, requirements)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "settlement unreachable",
                                                     "detail": str(e)[:160]})
    response_headers = {
        PAYMENT_RESPONSE_HEADER: b64(settlement.model_dump(exclude_none=True))
    }
    return JSONResponse(content=body, headers=response_headers)


@app.get("/evidence/{deal}")
def evidence(deal: str) -> Response:
    """The free receipt: the exact bytes the payment bought, for the court."""
    body = REPORTS.get(deal)
    if body is None:
        return JSONResponse(status_code=404, content={"error": "no such receipt"})
    return JSONResponse(content=body)


@app.get("/")
def index() -> Response:
    return JSONResponse(content={
        "service": "the-paid-answer",
        "route": "GET /report?quality=good|bad",
        "receipts": "GET /evidence/<deal>",
        "price": "$0.01 USDC on Base Sepolia",
        "payTo": PAY_TO,
    })


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8402)
    parser.add_argument("--pay-to", default=PAY_TO)
    args = parser.parse_args()
    PAY_TO = args.pay_to
    BASE_URL = f"http://127.0.0.1:{args.port}"
    uvicorn.run(app, host="127.0.0.1", port=args.port)
