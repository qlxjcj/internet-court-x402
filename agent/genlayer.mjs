// The court, through a thin node helper.
//
//   node agent/genlayer.mjs open   <seller> <report_url> <field> <tol_bps> <escrow_wei>
//   node agent/genlayer.mjs settle <deal_id>
//   node agent/genlayer.mjs deal   <deal_id>
//
// Reads go through the RPC; writes are signed with the buyer's key. The helper
// prints one line of JSON so the Python side never has to parse a receipt, and
// it retries on transport failures - the network drops calls often enough that
// a single attempt proves nothing. Writes are idempotent from the contract's
// point of view: a deal opens once and settles once.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { createClient, chains, createAccount } = require("genlayer-js");

const RPC = process.env.GENLAYER_RPC || "https://studio.genlayer.com/api";
const CHAIN = process.env.GENLAYER_CHAIN === "bradbury" ? chains.testnetBradbury
  : process.env.GENLAYER_CHAIN === "asimov" ? chains.testnetAsimov : chains.studionet;
const CONTRACT = process.env.COURT_ADDRESS;
const WALLET = fileURLToPath(new URL("./wallet.json", import.meta.url));

const [cmd, ...args] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function buyerKey() {
  const data = JSON.parse(readFileSync(WALLET, "utf8"));
  const key = data.private_key;
  return key.startsWith("0x") ? key : "0x" + key;
}

function client() {
  return createClient({ chain: CHAIN, endpoint: RPC, account: createAccount(buyerKey()) });
}

async function sendWithRetry(label, build, attempts = 6) {
  let last;
  for (let i = 0; i < attempts; i++) {
    try {
      return await build();
    } catch (e) {
      last = e;
      const m = String(e.message || e);
      // a contract-level refusal is final; only transport failures are retried
      if (!/fetch failed|Internal error|ECONNRESET|timeout|unknown RPC|429/i.test(m)) throw e;
      await sleep(5000 * (i + 1));
    }
  }
  throw last;
}

async function main() {
  if (!CONTRACT) throw new Error("set COURT_ADDRESS to the deployed court");
  const c = client();

  if (cmd === "open") {
    const [seller, reportUrl, field, tol, escrow] = args;
    const before = Number(await sendWithRetry("count",
      () => c.readContract({ address: CONTRACT, functionName: "get_deal_count", args: [] })));
    await sendWithRetry("open", () => c.writeContract({
      address: CONTRACT,
      functionName: "open_deal",
      args: [seller, reportUrl, field, Number(tol)],
      value: BigInt(escrow),
    }));
    for (let i = 0; i < 40; i++) {
      await sleep(4000);
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
    await sendWithRetry("settle", () => c.writeContract({
      address: CONTRACT, functionName: "settle", args: [dealId],
    }));
    for (let i = 0; i < 40; i++) {
      await sleep(4000);
      const deal = String(await sendWithRetry("read",
        () => c.readContract({ address: CONTRACT, functionName: "get_deal", args: [dealId] })));
      const status = /"status": "([A-Z]+)"/.exec(deal);
      if (status && status[1] !== "OPEN") {
        const verdict = String(await sendWithRetry("read",
          () => c.readContract({ address: CONTRACT, functionName: "get_verdict", args: [dealId] })));
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
