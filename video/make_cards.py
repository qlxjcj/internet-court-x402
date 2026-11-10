"""Generate the video cards as HTML, then render them with headless Chrome.

One shared design language across all six cards: dark ground, large type, the
three logos where the eye expects them. The cards are static; the motion comes
from the ffmpeg pass (slow zoom, crossfade, a moving accent).
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
OUT = os.path.join(HERE, "frames")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

STYLE = """
  :root { --bg:#0a0e14; --ink:#eef2f8; --dim:#8b98a8; --acc:#6aa8ff;
          --ok:#58d6a0; --bad:#ff6b6b; --gold:#e8c060; }
  * { box-sizing:border-box; margin:0; padding:0; }
  html, body { width:1920px; height:1080px; overflow:hidden; }
  body { background:radial-gradient(1200px 700px at 20% -10%, #16202e 0%, var(--bg) 60%);
         color:var(--ink); font:400 34px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;
         position:relative; }
  .wrap { position:absolute; inset:0; padding:96px 120px; display:flex;
          flex-direction:column; justify-content:center; }
  .eyebrow { font-size:26px; letter-spacing:.22em; text-transform:uppercase;
             color:var(--acc); font-weight:600; margin-bottom:26px; }
  h1 { font-size:112px; line-height:1.02; letter-spacing:-.035em; font-weight:700; }
  h2 { font-size:82px; line-height:1.06; letter-spacing:-.03em; font-weight:700; }
  .lede { font-size:40px; color:var(--dim); margin-top:30px; max-width:1180px; }
  .big { font-size:64px; letter-spacing:-.02em; font-weight:650; }
  .mono { font-family:"SF Mono",Consolas,monospace; }
  .row { display:flex; gap:48px; align-items:center; }
  .logos { position:absolute; top:64px; right:110px; display:flex; gap:40px;
           align-items:center; opacity:.95; }
  .logos img { height:52px; }
  .footer { position:absolute; left:120px; right:120px; bottom:56px;
            display:flex; justify-content:space-between; align-items:center;
            color:var(--dim); font-size:24px; letter-spacing:.06em; }
  .card { background:rgba(255,255,255,.045); border:1px solid rgba(255,255,255,.09);
          border-radius:22px; padding:34px 40px; }
  .term { background:#05070a; border:1px solid #1c2530; border-radius:18px;
          padding:30px 36px; font-family:"SF Mono",Consolas,monospace; font-size:27px;
          line-height:1.75; color:#c9d6e4; }
  .k { color:var(--acc); } .g { color:var(--ok); } .r { color:var(--bad); }
  .w { color:#fff; } .d { color:var(--dim); }
  .pill { display:inline-block; padding:8px 20px; border-radius:999px;
          font-size:26px; font-weight:650; letter-spacing:.04em; }
  .pill.ok { background:rgba(88,214,160,.16); color:var(--ok); }
  .pill.bad { background:rgba(255,107,107,.16); color:var(--bad); }
  .bar { height:16px; border-radius:9px; background:rgba(255,255,255,.10); overflow:hidden; }
  .bar > i { display:block; height:100%; background:linear-gradient(90deg,var(--acc),var(--ok)); }
  table { border-collapse:collapse; font-size:31px; }
  td, th { padding:14px 26px; text-align:left; border-bottom:1px solid rgba(255,255,255,.10); }
  th { color:var(--dim); font-size:22px; letter-spacing:.12em; text-transform:uppercase; }
  .stack { display:flex; flex-direction:column; gap:22px; }
"""


def page(inner: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{STYLE}</style></head>
<body>{inner}</body></html>"""


def logos(height: int = 52) -> str:
    return (
        '<div class="logos">'
        f'<img src="../assets/internet-court.svg" style="height:{height}px">'
        f'<img src="../assets/genlayer.svg" style="height:{height}px">'
        f'<img src="../assets/x402.svg" style="height:{height}px">'
        "</div>"
    )


def footer(left: str, right: str) -> str:
    return f'<div class="footer"><span>{left}</span><span>{right}</span></div>'


CARDS = [
    ("01-title", page(f"""
      {logos(56)}
      <div class="wrap">
        <div class="eyebrow">Internet Court &nbsp;·&nbsp; x402 &nbsp;·&nbsp; GenLayer</div>
        <h1>The Disputed<br>Answer</h1>
        <div class="lede">An agent buys an answer with an HTTP 402 micropayment.
          The answer is wrong. A court reads the evidence and moves the money.</div>
      </div>
      {footer("A BUILDERS WORKING GROUP MISSION", "45 SECONDS")}
    """)),

    ("02-buy", page(f"""
      {logos()}
      <div class="wrap">
        <div class="eyebrow">1 &nbsp;—&nbsp; the payment</div>
        <h2>The agent asks a paid API<br>for one ETH/USD report.</h2>
        <div class="row" style="margin-top:52px">
          <div class="term" style="width:920px">
            <div><span class="d">GET</span> <span class="w">/report?quality=good</span></div>
            <div><span class="r">HTTP/1.1 402 Payment Required</span></div>
            <div><span class="k">PAYMENT-REQUIRED</span> <span class="d">scheme=exact network=eip155:84532</span></div>
            <div><span class="d">amount</span> <span class="w">10000</span> <span class="d">(0.01 USDC)</span> <span class="d">→</span> <span class="g">EIP-3009</span></div>
          </div>
          <div class="stack">
            <div class="card"><div class="d" style="font-size:22px">THE MANDATE</div>
              <div class="big" style="margin-top:8px">price must sit within</div>
              <div class="big" style="color:var(--acc)">50 bps of both feeds</div></div>
            <div class="card"><div class="d" style="font-size:22px">THE ESCROW</div>
              <div class="big" style="margin-top:8px">0.1 GEN</div>
              <div class="d">held by the court</div></div>
          </div>
        </div>
      </div>
      {footer("REAL x402 · BASE SEPOLIA · TESTNET USDC", "01 / 05")}
    """)),

    ("03-paid", page(f"""
      {logos()}
      <div class="wrap">
        <div class="eyebrow">2 &nbsp;—&nbsp; the answer</div>
        <h2>It pays. The seller answers.</h2>
        <div class="row" style="margin-top:52px">
          <div class="term" style="width:1000px">
            <div><span class="k">PAYMENT-SIGNATURE</span> <span class="d">0x8b3f…c21a</span></div>
            <div><span class="g">HTTP/1.1 200 OK</span> <span class="d">settled 0.01 USDC</span></div>
            <div style="margin-top:14px"><span class="d">{{</span> <span class="k">"symbol"</span><span class="d">:</span> <span class="g">"ETH/USD"</span><span class="d">,</span></div>
            <div><span class="d">  </span><span class="k">"price"</span><span class="d">:</span> <span class="r">2294.94</span><span class="d">,</span></div>
            <div><span class="d">  </span><span class="k">"window"</span><span class="d">:</span> <span class="g">"24h"</span> <span class="d">}}</span></div>
            <div style="margin-top:14px"><span class="d">receipt published at</span> <span class="w">raw.githubusercontent.com/…</span></div>
          </div>
          <div class="stack" style="flex:1">
            <div class="card"><div class="d" style="font-size:22px">COINGECKO &nbsp;·&nbsp; COINBASE</div>
              <div class="big">2085.39</div>
              <div class="d">spot the seller read</div></div>
            <div class="card" style="border-color:rgba(255,107,107,.4)">
              <div class="d" style="font-size:22px">THE CLAIM</div>
              <div class="big" style="color:var(--bad)">2294.94 &nbsp;+10.06%</div></div>
            <div class="card"><div class="d" style="font-size:22px">THE ESCROW</div>
              <div class="big">0.1 GEN</div>
              <div class="d">held by the court</div></div>
          </div>
        </div>
      </div>
      {footer("REAL x402 SETTLEMENT ON BASE SEPOLIA · RECEIPT PUBLISHED", "02 / 05")}
    """)),

    ("04-dispute", page(f"""
      {logos()}
      <div class="wrap">
        <div class="eyebrow">3 &nbsp;—&nbsp; the dispute</div>
        <h2>Outside the band.<br>It goes to court.</h2>
        <div class="row" style="margin-top:52px; align-items:stretch">
          <div class="card" style="flex:1">
            <div class="d" style="font-size:22px">THE QUESTION</div>
            <div class="big" style="margin-top:12px">Is the claim inside the band<br>of <span style="color:var(--acc)">both</span> feeds?</div>
            <div class="bar" style="margin-top:34px"><i style="width:100%"></i></div>
            <div class="row" style="margin-top:18px; font-size:26px">
              <span class="d">1950</span><span class="d" style="margin-left:auto">2100</span><span class="d" style="margin-left:auto">2250</span>
            </div>
            <div class="d" style="margin-top:10px;font-size:24px">the band the buyer agreed to</div>
          </div>
          <div class="term" style="width:760px">
            <div><span class="k">validator 1</span> <span class="d">fetching…</span></div>
            <div><span class="k">validator 2</span> <span class="d">fetching…</span></div>
            <div><span class="k">validator 3</span> <span class="d">fetching…</span></div>
            <div style="margin-top:12px"><span class="d">report</span> <span class="w">2294.94</span></div>
            <div><span class="d">feed a </span> <span class="w">2085.39</span></div>
            <div><span class="d">feed b </span> <span class="w">2085.39</span></div>
            <div style="margin-top:12px"><span class="r">drift 1006 bps &gt; 50 bps</span></div>
          </div>
        </div>
      </div>
      {footer("CONSENSUS BINDS THE VERDICT — NEVER THE PRICE", "03 / 05")}
    """)),

    ("05-verdict", page(f"""
      {logos()}
      <div class="wrap">
        <div class="eyebrow">4 &nbsp;—&nbsp; the verdict, on chain</div>
        <h2><span class="r">OUTSIDE THE BAND.</span><br>The escrow goes back.</h2>
        <div class="row" style="margin-top:52px">
          <div class="card" style="width:500px">
            <div class="d" style="font-size:22px">SELLER</div>
            <div class="big" style="margin-top:10px">+0.0000 GEN</div>
            <div class="pill bad" style="margin-top:14px">paid: 0</div>
          </div>
          <div style="font-size:70px; color:var(--dim)">→</div>
          <div class="card" style="width:500px;border-color:rgba(88,214,160,.4)">
            <div class="d" style="font-size:22px">BUYER</div>
            <div class="big" style="margin-top:10px;color:var(--ok)">+0.1000 GEN</div>
            <div class="pill ok" style="margin-top:14px">refunded</div>
          </div>
          <div class="stack" style="flex:1">
            <div class="term" style="font-size:23px">
              <div><span class="k">settle</span>(<span class="d">d2</span>)</div>
              <div><span class="g">CANCELLED</span> <span class="d">· the claim is outside the band</span></div>
              <div><span class="d">paid 0 · refunded 0.1 · held 0</span></div>
            </div>
            <div class="card">
              <div class="d" style="font-size:22px">THE COURT</div>
              <div class="mono" style="margin-top:8px;font-size:24px">0xD2334f0eC96587b24E73C009227d9055074d0139</div>
              <div class="d" style="margin-top:6px;font-size:22px">GenLayer Studio · deal d2</div>
            </div>
          </div>
        </div>
      </div>
      {footer("THE HONEST RUN PAID THE SELLER · THIS ONE REFUNDED THE BUYER", "04 / 05")}
    """)),

    ("06-close", page(f"""
      {logos(64)}
      <div class="wrap">
        <div class="eyebrow">5 &nbsp;—&nbsp; reproduce it</div>
        <h2>One skill.<br>Anyone can rerun it.</h2>
        <div class="row" style="margin-top:52px">
          <div class="term" style="width:1100px">
            <div><span class="d">$</span> <span class="w">python agent/run_deal.py --quality good</span></div>
            <div><span class="g">  SETTLED   the claim matches both feeds   → seller +0.1 GEN</span></div>
            <div><span class="d">$</span> <span class="w">python agent/run_deal.py --quality bad</span></div>
            <div><span class="r">  CANCELLED the claim is outside the band → buyer +0.1 GEN</span></div>
          </div>
          <div class="stack">
            <div class="card"><div class="d" style="font-size:22px">REPOSITORY</div>
              <div class="big" style="margin-top:8px;font-size:38px">github.com/qlxjcj/<br>internet-court-x402</div></div>
            <div class="card"><div class="d" style="font-size:22px">CONTRACT TESTS</div>
              <div class="big" style="margin-top:8px">38 passed</div></div>
          </div>
        </div>
      </div>
      {footer("INTERNET COURT × x402 × GENLAYER", "05 / 05")}
    """)),
]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    made = []
    for name, html in CARDS:
        path = os.path.join(OUT, name + ".html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        png = os.path.join(OUT, name + ".png")
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                        "--window-size=1920,1080", f"--screenshot={png}",
                        "file:///" + path.replace("\\", "/")],
                       check=False, capture_output=True)
        if os.path.exists(png):
            made.append(png)
            print("rendered", os.path.basename(png), os.path.getsize(png))
        else:
            print("MISSING", name)
    return 0 if len(made) == len(CARDS) else 1


if __name__ == "__main__":
    sys.exit(main())
