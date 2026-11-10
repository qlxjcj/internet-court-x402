# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from genlayer import *

# GEN in wei (10**18) is the only asset. The deal is priced in GEN; the report
# itself is bought over x402, and this contract is only the court: it decides
# who keeps the escrow.
#
# Consensus binds the verdict and nothing else. Prices are values that keep
# moving, so a round that votes on a number fails the moment the chain moves;
# a round that votes on "was the claim inside the band of both sources" does
# not. The numbers are stored for the record, the verdict is what pays.

GEN_DECIMALS = 18
OPEN = "OPEN"
SETTLED = "SETTLED"
CANCELLED = "CANCELLED"
MAX_TOLERANCE_BPS = 2000

# Two independent price feeds, fixed in the contract so neither party can point
# the court at a server it controls. `%` is where the field value goes.
SRC_A = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
SRC_B = "https://api.coinbase.com/v2/prices/ETH-USD/spot"


class DeliveryAdjudicator(gl.Contract):
    """The court for a paid answer.

    A buyer escrows GEN and freezes where the answer must live, which field it
    must carry, and how far that field may drift from two independent feeds.
    Anyone may then call settle: the contract fetches the answer and both
    feeds, and pays the seller only when the answer is really there and really
    inside the band. Otherwise the escrow goes back to the buyer."""

    deals: TreeMap[str, str]
    verdicts: TreeMap[str, str]
    deal_count: u256

    def __init__(self):
        self.deal_count = 0

    def _addr_hex(self, a) -> str:
        if isinstance(a, str):
            return a
        h = getattr(a, "as_hex", None)
        if isinstance(h, str):
            return h
        if isinstance(a, (bytes, bytearray)):
            return "0x" + bytes(a).hex()
        return str(a)

    def _is_evm(self, a) -> bool:
        if not isinstance(a, str) or not a.startswith("0x") or len(a) != 42:
            return False
        try:
            int(a[2:], 16)
        except ValueError:
            return False
        return True

    def _url(self, u) -> str:
        s = str(u).strip()
        if not (s.startswith("https://") or s.startswith("http://")):
            return ""
        if len(s) > 400 or " " in s:
            return ""
        return s

    def _body(self, content) -> str:
        b = getattr(content, "body", None)
        if b is None:
            return str(content)
        return b.decode("utf-8", errors="replace") if isinstance(b, bytes) else str(b)

    def _transfer(self, to: Address, amount: int):
        if amount > 0:
            gl.get_contract_at(to).emit_transfer(value=u256(amount))

    def _load(self, did: str) -> dict:
        raw = self.deals.get(str(did), "")
        if not raw:
            raise gl.vm.UserError("Deal not found")
        return json.loads(raw)

    def _save(self, d: dict):
        self.deals[d["deal_id"]] = json.dumps(d)

    def _float(self, v) -> float:
        try:
            x = float(str(v).strip())
        except Exception:
            return -1.0
        return x

    def _feed_value(self, body: str, path: list) -> float:
        """Follow a fixed JSON path to a number.

        -2 when the body is not JSON at all (the feed could not be read),
        -1 when the path or the number is missing (the feed carried no price)."""
        try:
            node = json.loads(body)
        except Exception:
            return -2.0
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return -1.0
            node = node[key]
        return self._float(node)

    def _report_value(self, body: str, field: str) -> tuple:
        """Extract the number the report claims for `field`.

        The model is only allowed to *point at* text: the value it returns must
        appear verbatim in the report body, so a model can lose this deal for
        the seller but can never invent a number that would win it."""
        try:
            raw = json.loads(body)
        except Exception:
            raw = None
        if isinstance(raw, dict) and str(field) in raw:
            v = self._float(raw[str(field)])
            return v, str(raw[str(field)]).strip()
        prompt = (
            "You are extracting one number from a report. "
            "Return only the number the report states for the field '" + str(field) + "'. "
            "Return the digits exactly as written in the text, no words, no units.\n\n"
            "REPORT:\n" + str(body)[:2000]
        )
        out = ""
        try:
            out = str(gl.nondet.exec_prompt(prompt)).strip()
        except Exception:
            out = ""
        if not out:
            return -1.0, ""
        # the empty-string trap: "" is a substring of everything
        if not out or out not in str(body):
            return -1.0, ""
        return self._float(out), out

    def _agree(self, his, mine) -> bool:
        """The round binds the verdict and its reason code - nothing else."""
        if not isinstance(his, dict) or not isinstance(mine, dict):
            return False
        return (str(mine.get("verdict")) == str(his.get("verdict"))
                and str(mine.get("reason")) == str(his.get("reason")))

    # ---------------- the verdict, as a boolean ----------------

    def _judgement(self, d: dict) -> dict:
        """One round, one question: does the answer hold up?

        Only this boolean and a reason code are compared between validators.
        The feeds are live, so the numbers underneath them are expected to move
        between reads; the band test is not."""
        report_url = str(d["report_url"])
        field = str(d["field"])
        tol = int(d["tolerance_bps"])

        def run() -> dict:
            bodies = {}
            for key, url in (("report", report_url), ("a", SRC_A), ("b", SRC_B)):
                body = ""
                try:
                    body = self._body(gl.nondet.web.get(url))
                except Exception:
                    body = ""
                bodies[key] = body
            if not bodies["report"].strip():
                return {"verdict": False, "reason": "no answer was delivered"}
            if not bodies["a"] or not bodies["b"]:
                return {"verdict": False, "reason": "a feed could not be read"}
            claimed, verbatim = self._report_value(bodies["report"], field)
            if claimed <= 0 or not verbatim:
                return {"verdict": False, "reason": "the answer carries no usable value"}
            va = self._feed_value(bodies["a"], ["ethereum", "usd"])
            vb = self._feed_value(bodies["b"], ["data", "amount"])
            if va == -2.0 or vb == -2.0:
                return {"verdict": False, "reason": "a feed could not be read"}
            if va <= 0 or vb <= 0:
                return {"verdict": False, "reason": "a feed carried no price"}
            worst = 0
            for v in (va, vb):
                drift = abs(claimed - v) * 10000.0 / v
                if drift > worst:
                    worst = drift
            if worst > float(tol):
                return {"verdict": False, "reason": "the claim is outside the band"}
            return {"verdict": True, "reason": "the claim matches both feeds"}

        def agrees(leader) -> bool:
            return isinstance(leader, gl.vm.Return) and self._agree(leader.calldata, run())

        res = gl.vm.run_nondet_unsafe(run, agrees)
        return res if isinstance(res, dict) else {"verdict": False, "reason": "no verdict"}

    # ---------------- lifecycle ----------------

    @gl.public.write.payable
    def open_deal(self, seller: str, report_url: str, field: str,
                  tolerance_bps: int) -> str:
        """Escrow the value of a deal and freeze what a good answer must be."""
        buyer = self._addr_hex(gl.message.sender_address)
        escrow = int(gl.message.value)
        if escrow <= 0:
            raise gl.vm.UserError("Escrow must be > 0 wei")
        if not self._is_evm(seller) or self._addr_hex(seller).lower() == buyer.lower():
            raise gl.vm.UserError("Seller must be another 0x address")
        url = self._url(report_url)
        if not url:
            raise gl.vm.UserError("Give a real https URL for the answer")
        name = str(field).strip()
        if not name or len(name) > 40:
            raise gl.vm.UserError("Name the field to check")
        try:
            tol = int(tolerance_bps)
        except Exception:
            raise gl.vm.UserError("Tolerance must be an integer")
        if not 1 <= tol <= MAX_TOLERANCE_BPS:
            raise gl.vm.UserError("Tolerance must be 1.." + str(MAX_TOLERANCE_BPS) + " bps")
        did = "d" + str(int(self.deal_count))
        self.deals[did] = json.dumps({
            "deal_id": did, "buyer": buyer, "seller": self._addr_hex(seller).lower(),
            "report_url": url, "field": name, "tolerance_bps": tol,
            "escrow": escrow, "status": OPEN, "reason": "", "paid": 0, "refunded": 0,
            "feeds": [SRC_A, SRC_B],
            "units": {"asset": "GEN", "amount_decimals": GEN_DECIMALS,
                      "tolerance": "basis points of the feed value"},
        })
        self.deal_count = u256(int(self.deal_count) + 1)
        return did

    @gl.public.write
    def settle(self, deal_id: str) -> str:
        """Anyone may ask the court to rule; the verdict moves the escrow."""
        d = self._load(deal_id)
        if str(d["status"]) != OPEN:
            raise gl.vm.UserError("Deal is " + str(d["status"]))
        res = self._judgement(d)
        self.verdicts[deal_id] = json.dumps(res)
        d["reason"] = str(res.get("reason", "no verdict"))
        if res.get("verdict") is True:
            d["status"] = SETTLED
            d["paid"] = int(d["escrow"])
            self._save(d)
            self._transfer(Address(d["seller"]), int(d["escrow"]))
            return SETTLED
        d["status"] = CANCELLED
        d["refunded"] = int(d["escrow"])
        self._save(d)
        self._transfer(Address(d["buyer"]), int(d["escrow"]))
        return CANCELLED

    @gl.public.write
    def cancel(self, deal_id: str) -> str:
        """The buyer may withdraw before anyone asks for a verdict."""
        d = self._load(deal_id)
        if str(d["status"]) != OPEN:
            raise gl.vm.UserError("Deal is " + str(d["status"]))
        if self._addr_hex(gl.message.sender_address).lower() != str(d["buyer"]).lower():
            raise gl.vm.UserError("Only the buyer cancels")
        d["status"] = CANCELLED
        d["reason"] = "cancelled by the buyer"
        d["refunded"] = int(d["escrow"])
        self._save(d)
        self._transfer(Address(d["buyer"]), int(d["escrow"]))
        return CANCELLED

    # ---------------- views ----------------

    @gl.public.view
    def get_deal(self, deal_id: str) -> str:
        d = self._load(deal_id)
        d["held"] = 0 if str(d["status"]) != OPEN else int(d["escrow"])
        return json.dumps(d)

    @gl.public.view
    def get_verdict(self, deal_id: str) -> str:
        self._load(deal_id)
        return str(self.verdicts.get(str(deal_id), "")) or "{}"

    @gl.public.view
    def get_deal_count(self) -> int:
        return int(self.deal_count)

    @gl.public.view
    def quote_band(self, tolerance_bps: int) -> str:
        """Pure arithmetic on the tolerance, for the page before it escrows."""
        try:
            tol = int(tolerance_bps)
        except Exception:
            tol = 0
        return json.dumps({"tolerance_bps": tol,
                           "upper_multiple": 1 + tol / 10000.0,
                           "lower_multiple": 1 - tol / 10000.0})
