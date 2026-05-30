import requests

address = "17VSgeazX2nz4kfEjG5o5Tt6TUqHkWXs7U"

txs = requests.get(
    f"https://blockstream.info/api/address/{address}/txs",
    timeout=20
).json()

print(f"Transactions involving {address}: {len(txs)}")

for tx in txs:
    print("=" * 100)
    print("TRANSACTION ID:", tx["txid"])

    received = 0
    spent = 0
    input_total = 0
    output_total = 0

    for vin in tx.get("vin", []):
        prev = vin.get("prevout") or {}
        val = prev.get("value", 0) / 100_000_000
        input_total += val

        if prev.get("scriptpubkey_address") == address:
            spent += val

    for vout in tx.get("vout", []):
        val = vout.get("value", 0) / 100_000_000
        output_total += val

        if vout.get("scriptpubkey_address") == address:
            received += val

    print("Inputs:", len(tx.get("vin", [])))
    print("Outputs:", len(tx.get("vout", [])))
    print("Received by address:", received)
    print("Spent by address:", spent)
    print("Total tx input:", input_total)
    print("Total tx output:", output_total)

    if received > 0 and spent == 0:
        print("-> RECEIVED")

    elif spent > 0 and received == 0:
        print("-> SPENT")

    elif received > 0 and spent > 0:
        print("-> BOTH")