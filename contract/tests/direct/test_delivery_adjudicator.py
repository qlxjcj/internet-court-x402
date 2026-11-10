"""Direct-mode tests for the Delivery Adjudicator.

Groups:

  A  creation   -- escrow the value, freeze what a good answer must be
  B  verdict    -- the claim must match BOTH feeds, inside the band
  C  fabrication-- the model may point at text, never invent a number
  D  consensus  -- the round binds the verdict, not the moving prices
  E  money      -- who keeps the escrow, and what the ledger must always show
  F  invariants -- refusals change nothing, views are strings
"""

import json

import pytest

from conftest import (
    BASE,
    BUYER,
    ESCROW,
    FIELD,
    REPORT_URL,
    SELLER,
    STRANGER,
    TOL,
    balance,
    cancel,
    coinbase,
    coingecko,
    contract_balance,
    deal,
    open_deal,
    remock,
    report,
    settle,
    snapshot,
    verdict,
)


# ==========================================================================
# A. creation
# ==========================================================================

def test_opening_escrows_the_value_and_freezes_the_terms(court):
    vm, c = court
    before = balance(vm, BUYER)
    did = open_deal(vm, c)
    d = deal(vm, c, did)
    assert contract_balance(vm) == ESCROW
    assert balance(vm, BUYER) == before - ESCROW
    assert d["escrow"] == ESCROW and d["paid"] == 0 and d["refunded"] == 0
    assert d["report_url"] == REPORT_URL
    assert d["field"] == FIELD
    assert d["tolerance_bps"] == TOL
    assert d["feeds"] == [
        "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
        "https://api.coinbase.com/v2/prices/ETH-USD/spot",
    ]


def test_the_unit_model_is_stored_with_the_deal(court):
    vm, c = court
    d = deal(vm, c, open_deal(vm, c))
    assert d["units"] == {"asset": "GEN", "amount_decimals": 18,
                          "tolerance": "basis points of the feed value"}
    assert d["held"] == ESCROW


def test_a_refused_open_moves_no_money(court):
    vm, c = court
    before = balance(vm, BUYER)
    with pytest.raises(Exception):
        open_deal(vm, c, escrow=0)
    assert balance(vm, BUYER) == before
    assert contract_balance(vm) == 0
    assert c.get_deal_count() == 0


@pytest.mark.parametrize("kw", [
    {"seller": BUYER}, {"seller": "0x1234"},
    {"report_url": "ftp://x/y"}, {"report_url": "not a url"}, {"report_url": ""},
    {"field": ""}, {"field": "x" * 41},
    {"tolerance": 0}, {"tolerance": 2001},
])
def test_rejects_bad_terms(court, kw):
    vm, c = court
    with pytest.raises(Exception):
        open_deal(vm, c, **kw)
    assert c.get_deal_count() == 0
    assert contract_balance(vm) == 0


def test_the_seller_cannot_be_the_buyer(court):
    vm, c = court
    with pytest.raises(Exception):
        open_deal(vm, c, seller=BUYER)
    assert c.get_deal_count() == 0


# ==========================================================================
# B. verdict: the claim has to hold up against both feeds
# ==========================================================================

def test_a_claim_inside_the_band_pays_the_seller(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2505.0))
    before = balance(vm, SELLER)
    assert settle(vm, c, did) == "SETTLED"
    d = deal(vm, c, did)
    assert d["status"] == "SETTLED"
    assert d["reason"] == "the claim matches both feeds"
    assert d["paid"] == ESCROW and d["refunded"] == 0
    assert balance(vm, SELLER) == before + ESCROW
    assert contract_balance(vm) == 0


def test_a_claim_outside_the_band_refunds_the_buyer(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2700.0))
    before = balance(vm, BUYER)
    assert settle(vm, c, did) == "CANCELLED"
    d = deal(vm, c, did)
    assert d["status"] == "CANCELLED"
    assert d["reason"] == "the claim is outside the band"
    assert d["refunded"] == ESCROW and d["paid"] == 0
    assert balance(vm, BUYER) == before + ESCROW
    assert contract_balance(vm) == 0


def test_a_claim_matching_one_feed_but_not_the_other_is_refused(court):
    vm, c = court
    did = open_deal(vm, c)
    # 2490 is within 0.5% of 2500 but 2512 is not
    remock(vm, rep=report(2490.0), b=coinbase(2512.0))
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "the claim is outside the band"


def test_the_band_edge_is_inclusive(court):
    vm, c = court
    did = open_deal(vm, c)
    # 2512.5 is exactly 50 bps above 2500
    remock(vm, rep=report(2512.5))
    assert settle(vm, c, did) == "SETTLED"


def test_one_step_over_the_band_is_refused(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2520.0))
    assert settle(vm, c, did) == "CANCELLED"


def test_a_missing_answer_is_not_a_delivery(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep="")
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "no answer was delivered"


def test_a_feed_that_cannot_be_read_is_not_a_verdict(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, b="<html>502 Bad Gateway</html>")
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "a feed could not be read"


def test_a_feed_with_no_price_is_not_a_verdict(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, a=coingecko(usd=0))
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "a feed carried no price"


def test_a_report_without_the_field_is_refused(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=json.dumps({"symbol": "ETH/USD", "volume": 12}))
    assert settle(vm, c, did) == "CANCELLED"


def test_an_answer_may_only_be_settled_once(court):
    vm, c = court
    did = open_deal(vm, c)
    settle(vm, c, did)
    before = balance(vm, SELLER)
    with pytest.raises(Exception):
        settle(vm, c, did)
    assert balance(vm, SELLER) == before


# ==========================================================================
# C. fabrication: the model may point at text, never invent a number
# ==========================================================================

def test_a_text_answer_is_read_when_the_number_is_really_in_it(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2505.0, as_text=True))
    vm.mock_llm(".*price.*", "2505")
    assert settle(vm, c, did) == "SETTLED"
    assert deal(vm, c, did)["paid"] == ESCROW


def test_a_number_the_model_invents_never_counts(court):
    vm, c = court
    # the model says 2400, which is inside the band, but the report says 2700
    did = open_deal(vm, c)
    remock(vm, rep=report(2700.0, as_text=True))
    vm.mock_llm(".*price.*", "2400")
    assert settle(vm, c, did) == "CANCELLED"


def test_a_number_the_model_makes_up_out_of_thin_air_never_counts(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep="no price in this report at all")
    vm.mock_llm(".*price.*", "9999")
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "the answer carries no usable value"


def test_the_empty_string_is_never_a_quoted_value(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2505.0, as_text=True))
    vm.mock_llm(".*price.*", "")
    assert settle(vm, c, did) == "CANCELLED"
    assert verdict(vm, c, did)["reason"] == "the answer carries no usable value"


# ==========================================================================
# D. consensus binds the verdict, not the moving prices
# ==========================================================================

def test_the_verdict_and_its_reason_are_what_agreement_binds(court):
    vm, c = court
    a = {"verdict": True, "reason": "the claim matches both feeds"}
    assert c._agree(a, a) is True
    assert c._agree(a, {"verdict": True, "reason": "the claim is outside the band"}) is False
    assert c._agree(a, {"verdict": False, "reason": "the claim matches both feeds"}) is False
    assert c._agree(a, {"verdict": "True", "reason": "the claim matches both feeds"}) is True


def test_a_round_without_a_dict_is_never_agreed(court):
    vm, c = court
    a = {"verdict": True, "reason": "ok"}
    assert c._agree(a, None) is False
    assert c._agree(a, "nope") is False
    assert c._agree({"verdict": True}, {"verdict": True, "reason": "ok"}) is False


# ==========================================================================
# E. money
# ==========================================================================

def test_the_ledger_always_adds_up(court):
    vm, c = court
    a = open_deal(vm, c)
    remock(vm, rep=report(2505.0))
    settle(vm, c, a)
    b = open_deal(vm, c)
    remock(vm, rep=report(2700.0))
    settle(vm, c, b)
    for did in (a, b):
        d = deal(vm, c, did)
        assert d["paid"] + d["refunded"] == d["escrow"]
        assert d["held"] == 0
    assert contract_balance(vm) == 0


def test_the_buyer_may_cancel_before_anyone_rules(court):
    vm, c = court
    did = open_deal(vm, c)
    before = balance(vm, BUYER)
    vm.sender = BUYER
    assert c.cancel(did) == "CANCELLED"
    assert balance(vm, BUYER) == before + ESCROW
    assert contract_balance(vm) == 0


def test_only_the_buyer_cancels(court):
    vm, c = court
    did = open_deal(vm, c)
    for who in (SELLER, STRANGER):
        vm.sender = who
        with pytest.raises(Exception):
            c.cancel(did)
    assert deal(vm, c, did)["status"] == "OPEN"


def test_a_ruled_deal_cannot_be_cancelled(court):
    vm, c = court
    did = open_deal(vm, c)
    remock(vm, rep=report(2505.0))
    settle(vm, c, did)
    vm.sender = BUYER
    with pytest.raises(Exception):
        c.cancel(did)


def test_two_deals_never_mix(court):
    vm, c = court
    a = open_deal(vm, c, escrow=ESCROW)
    b = open_deal(vm, c, escrow=2 * ESCROW, seller=STRANGER)
    remock(vm, rep=report(2505.0))
    settle(vm, c, a)
    assert deal(vm, c, a)["paid"] == ESCROW
    assert deal(vm, c, b)["held"] == 2 * ESCROW
    assert contract_balance(vm) == 2 * ESCROW


# ==========================================================================
# F. invariants and views
# ==========================================================================

def test_every_refusal_leaves_the_state_byte_identical(court):
    vm, c = court
    did = open_deal(vm, c)
    before = snapshot(vm, c, did)
    remock(vm, rep="")
    with pytest.raises(Exception):
        settle(vm, c, "d99")
    vm.sender = STRANGER
    with pytest.raises(Exception):
        c.cancel(did)
    assert snapshot(vm, c, did) == before


def test_views_are_strings(court):
    vm, c = court
    did = open_deal(vm, c)
    for v in (c.get_deal(did), c.get_verdict(did), c.quote_band(TOL)):
        assert isinstance(v, str)
    assert c.get_verdict(did) == "{}"
    assert json.loads(c.quote_band(50))["upper_multiple"] == 1.005


def test_an_unknown_deal_raises(court):
    vm, c = court
    with pytest.raises(Exception):
        c.get_deal("d99")
    with pytest.raises(Exception):
        c.get_verdict("d99")
    with pytest.raises(Exception):
        settle(vm, c, "d99")


def test_deal_count_tracks_opens(court):
    vm, c = court
    assert c.get_deal_count() == 0
    open_deal(vm, c)
    open_deal(vm, c)
    assert c.get_deal_count() == 2
