import requests

seed = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"

url = f"https://blockstream.info/api/address/{seed}/txs"
txs = requests.get(url).json()

print(f"\nTransactions involving {seed}: {len(txs)}\n")

for tx in txs:
    print("=" * 100)
    print("TRANSACTION ID:", tx["txid"])

    seed_input_total = 0
    seed_output_total = 0

    print("\nINPUT ADDRESSES:")
    for vin in tx.get("vin", []):
        prevout = vin.get("prevout") or {}
        addr = prevout.get("scriptpubkey_address", "Unknown")
        value = prevout.get("value", 0) / 100_000_000

        print(f"  {addr}  -->  {value:.8f} BTC")

        if addr == seed:
            seed_input_total += value

    print("\nOUTPUT ADDRESSES:")
    for vout in tx.get("vout", []):
        addr = vout.get("scriptpubkey_address", "Unknown")
        value = vout.get("value", 0) / 100_000_000

        print(f"  {addr}  <--  {value:.8f} BTC")

        if addr == seed:
            seed_output_total += value

    print("\nSEED SUMMARY:")
    print(f"  BTC sent TO seed:   {seed_output_total:.8f}")
    print(f"  BTC sent FROM seed: {seed_input_total:.8f}")

    if seed_output_total > 0 and seed_input_total == 0:
        print("  --> Seed RECEIVED funds in this transaction")

    elif seed_input_total > 0:
        print("  --> Seed SPENT funds in this transaction")

print("=" * 100)