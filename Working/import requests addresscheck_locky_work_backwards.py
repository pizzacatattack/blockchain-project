import requests

address = "19J5etxY9rEcPkML16DMA3f9VKW4U5Su2x"

txs = requests.get(
    f"https://blockstream.info/api/address/{address}/txs"
).json()

print(f"Transactions involving {address}: {len(txs)}")

for tx in txs:
    print("=" * 100)
    print("TRANSACTION ID:", tx["txid"])

    received = 0
    spent = 0
    input_count = len(tx.get("vin", []))
    output_count = len(tx.get("vout", []))

    for vin in tx.get("vin", []):
        prev = vin.get("prevout") or {}
        if prev.get("scriptpubkey_address") == address:
            spent += prev["value"] / 100_000_000

    for vout in tx.get("vout", []):
        if vout.get("scriptpubkey_address") == address:
            received += vout["value"] / 100_000_000

    print("Inputs:", input_count)
    print("Outputs:", output_count)
    print("Received:", received)
    print("Spent:", spent)

    if received > 0 and spent == 0:
        print("-> RECEIVED")

    elif spent > 0 and received == 0:
        print("-> SPENT")

    elif spent > 0 and received > 0:
        print("-> BOTH (possible change / intermediary)")