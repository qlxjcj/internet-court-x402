"""Create the buyer wallet for the demo.

Writes `agent/wallet.json` (gitignored) with a fresh Base Sepolia key. The
buyer needs testnet USDC only: the x402 exact scheme is gasless, because the
facilitator sponsors the gas.
"""

import json
import os

from eth_account import Account

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallet.json")
if os.path.exists(path):
    data = json.load(open(path))
else:
    acct = Account.create()
    data = {"private_key": acct.key.hex(), "address": acct.address}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

print("buyer address:", data["address"])
print("saved:", path, "(gitignored)")
