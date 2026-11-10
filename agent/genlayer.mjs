// The court, through a thin node helper.
//
//   node agent/genlayer.mjs open   <seller> <report_url> <field> <tol_bps> <escrow_wei>
//   node agent/genlayer.mjs settle <deal_id>
//   node agent/genlayer.mjs deal   <deal_id>
//
// Reads go through the RPC; writes are signed with the buyer's key. The helper
// prints one line of JSON so the Python side never has to parse a receipt.

import { readFileSync } from "node:fs";
import { createClient, chains, createAccount } from "genlayer-js";

const RPC = process.env.GENLAYER_RPC || "https://studio.genlayer.com/api";
const CHAIN = process.env.GENLAYER_CHAIN === "asimov" ? chains.testnetAsimov : chains.studionet;
const CONTRACT = process.env.COURT_ADDRESS;
const WALLET = new URL("./wallet.json", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");

const [cmd, ...args] = process.argv.slice(2);

function buyerKey() {
  const data = JSON.parse(readFileSync(WALLET, "utf8"));
  return data.private_key;
}

function client() {
  return createClient({ chain: CHAIN, endpoint: RPC, account: createAccount(buyerKey()) });
}

const raw = (v) => {
  const s = String(v);
  return /^[0-9]+$/.test(s) ? BigInt(s) : s;
};

async function main() {
  if (!CONTRACT) throw new Error("set COURT_ADDRESS to the deployed court");
  const c = client();

  if (cmd === "open") {
    const [seller, reportUrl, field, tol, escrow] = args;
    const before = Number(await c.readContract({ address: CONTRACT, functionName: "get_deal_count", args: [] }));
    await c.writeContract({
      address: CONTRACT,
      functionName: "open_deal",
      args: [seller, reportUrl, field, Number(tol)],
      value: BigInt(escrow),
    });
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      const now = Number(await c.readContract({ address: CONTRACT, functionName: "get_deal_count", args: [] }));
      if (now > before) {
        console.log(JSON.stringify({ deal: "d" + (now - 1) }));
        return;
      }
    }
    throw new Error("the deal did not open in time");
  }

  if (cmd === "settle") {
    const [dealId] = args;
    await c.writeContract({ address: CONTRACT, functionName: "settle", args: [dealId] });
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      const deal = String(await c.readContract({ address: CONTRACT, functionName: "get_deal", args: [dealId] }));
      const status = /"status": "([A-Z]+)"/.exec(deal);
      if (status && status[1] !== "OPEN") {
        const verdict = String(await c.readContract({ address: CONTRACT, functionName: "get_verdict", args: [dealId] }));
        console.log(JSON.stringify({ status: status[1], verdict: JSON.parse(verdict || "{}"), deal: JSON.parse(deal) }));
        return;
      }
    }
    throw new Error("the court did not rule in time");
  }

  if (cmd === "deal") {
    const deal = String(await c.readContract({ address: CONTRACT, functionName: "get_deal", args: [args[0]] }));
    console.log(deal);
    return;
  }

  throw new Error("unknown command: " + cmd);
}

main().catch((e) => {
  console.error(String(e.message || e));
  process.exit(1);
});
