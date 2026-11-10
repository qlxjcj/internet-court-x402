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
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from x402.client import PaymentPayloadV1
from x402.http import HTTPFacilitatorClientSync
from x402.server import PaymentRequirementsV1

# Base Sepolia USDC, 6 decimals. Price is $0.01 per answer.
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
PRICE_UNITS = "10000"
NETWORK = "eip155:84532"          # Base Sepolia
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


def build_report(quality: str) -> dict:
    """What the buyer is paying for.

    `good` quotes a price inside the band of both feeds. `bad` quotes one that
    is far outside it - the difference between the two is the whole dispute.
    """
    price = HONEST_PRICE if quality == "good" else round(HONEST_PRICE * LIAR_MULTIPLIER, 2)
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
        extra={"assetTransferMethod": ASSET_TRANSFER_METHOD},
    )


def b64(obj) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


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

    verification = FACILITATOR_CLIENT.verify(payload, requirements)
    if not getattr(verification, "isValid", False):
        reason = getattr(verification, "invalidReason", "payment rejected")
        return JSONResponse(status_code=402, content={"error": str(reason)})

    deal = uuid.uuid4().hex[:12]
    body = build_report(quality)
    body["deal"] = deal
    REPORTS[deal] = body

    settlement = FACILITATOR_CLIENT.settle(payload, requirements)
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
