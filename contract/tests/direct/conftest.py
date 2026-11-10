"""Fixtures for the Delivery Adjudicator direct-mode tests.

The three fetches use the real shapes: the report is the seller's published
answer, CoinGecko returns `{"ethereum":{"usd": ...}}`, and Coinbase returns
`{"data":{"amount": "..."}}` with the price as a *string*. The judge must cope
with both.

Direct mode does not track native value flow, so the same two accounting hooks
are installed, and a refused payable call puts the value back.
"""

import json
import os

import pytest

CONTRACT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "delivery_adjudicator.py",
)

BUYER = "0x" + "aa" * 20
SELLER = "0x" + "bb" * 20
STRANGER = "0x" + "44" * 20

ESCROW = 10 ** 17                 # 0.1 GEN
REPORT_URL = "https://evidence.example.com/evidence/deal-1"
FIELD = "price"
TOL = 50                          # 50 bps = 0.5%
BASE = 2500.0


def report(price=BASE, field=FIELD, as_text=False):
    if as_text:
        return f"Daily ETH/USD report. {field}: {price} at close. Sources: two feeds."
    return json.dumps({"symbol": "ETH/USD", field: price, "window": "24h"})


def coingecko(usd=BASE):
    return json.dumps({"ethereum": {"usd": usd}})


def coinbase(amount=BASE):
    return json.dumps({"data": {"base": "ETH", "currency": "USD", "amount": str(amount)}})


def remock(vm, rep=None, a=None, b=None):
    vm.clear_mocks()
    vm.mock_web(r".*evidence\.example\.com/evidence/.*",
                {"method": "GET", "status": 200,
                 "body": report() if rep is None else rep})
    vm.mock_web(r".*coingecko.*",
                {"method": "GET", "status": 200,
                 "body": coingecko() if a is None else a})
    vm.mock_web(r".*coinbase.*",
                {"method": "GET", "status": 200,
                 "body": coinbase() if b is None else b})


@pytest.fixture
def court(direct_vm, direct_deploy):
    vm = direct_vm

    def _value_transfer_hook(vm, request):
        if "PostMessage" not in request:
            return None
        msg = request["PostMessage"]
        amount = int(msg.get("value", 0))
        if amount > 0:
            contract = vm._contract_address
            recipient = vm._to_bytes(msg["address"])
            vm._balances[contract] = vm._balances.get(contract, 0) - amount
            vm._balances[recipient] = vm._balances.get(recipient, 0) + amount
        return {"ok": None}

    vm._gl_call_hook = _value_transfer_hook

    remock(vm)
    c = direct_deploy(CONTRACT)

    def _wrap(fn):
        def inner(*args):
            paid = 0
            sender = vm._to_bytes(vm.sender)
            contract = vm._contract_address
            if vm.value > 0:
                vm._balances[sender] = vm._balances.get(sender, 0) - vm.value
                vm._balances[contract] = vm._balances.get(contract, 0) + vm.value
                paid = vm.value
            try:
                return fn(*args)
            except Exception:
                if paid:
                    vm._balances[sender] = vm._balances.get(sender, 0) + paid
                    vm._balances[contract] = vm._balances.get(contract, 0) - paid
                raise
        return inner

    c.open_deal = _wrap(c.open_deal)

    for addr in (BUYER, SELLER, STRANGER):
        vm.deal(addr, 100 * ESCROW)
    return vm, c


def balance(vm, addr):
    return vm._balances.get(vm._to_bytes(addr), 0)


def contract_balance(vm):
    return vm._balances.get(vm._contract_address, 0)


def open_deal(vm, c, seller=SELLER, report_url=REPORT_URL, field=FIELD,
              tolerance=TOL, escrow=ESCROW, sender=BUYER):
    vm.sender = sender
    vm.value = escrow
    try:
        return c.open_deal(seller, report_url, field, tolerance)
    finally:
        vm.value = 0


def settle(vm, c, did, sender=STRANGER):
    vm.sender = sender
    return c.settle(did)


def cancel(vm, c, did, sender=BUYER):
    vm.sender = sender
    return c.cancel(did)


def deal(vm, c, did):
    return json.loads(c.get_deal(did))


def verdict(vm, c, did):
    return json.loads(c.get_verdict(did))


def snapshot(vm, c, did):
    return (c.get_deal(did), c.get_verdict(did))
