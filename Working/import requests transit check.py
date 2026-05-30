import requests

txid = "09c090cbe7be5951bcbc6f3c3b4a82db27f948f1ffa003bf1cde353a4d58811f"

tx = requests.get(
    f"https://blockstream.info/api/tx/{txid}",
    timeout=20
).json()

for vout in tx["vout"]:
    addr = vout.get("scriptpubkey_address")
    btc = vout["value"] / 100_000_000
    print(addr, btc)