import requests

candidate = "19J5etxY9rEcPkML16DMA3f9VKW4U5Su2x"
txid = "275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"

tx = requests.get(
    f"https://blockstream.info/api/tx/{txid}",
    timeout=20
).json()

all_inputs = []

for vin in tx["vin"]:
    prev = vin.get("prevout") or {}
    addr = prev.get("scriptpubkey_address")
    if addr:
        all_inputs.append(addr)

print("Candidate in transaction?", candidate in all_inputs)