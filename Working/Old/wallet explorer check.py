import requests

txid = "69affd84d73a7bbf644fe9defa18bab740b76487c07b636a6bb4a50689d8e8e3"

url = f"https://blockstream.info/api/tx/{txid}"
tx = requests.get(url).json()

print("=" * 100)
print("TRANSACTION ID:", tx["txid"])

print("\nINPUT ADDRESSES:")
total_in = 0

for vin in tx.get("vin", []):
    prevout = vin.get("prevout") or {}
    addr = prevout.get("scriptpubkey_address", "Unknown")
    value = prevout.get("value", 0) / 100_000_000
    total_in += value

    print(f"  {addr}  -->  {value:.8f} BTC")

print(f"\nTOTAL INPUT BTC: {total_in:.8f}")

print("\nOUTPUT ADDRESSES:")
total_out = 0

for vout in tx.get("vout", []):
    addr = vout.get("scriptpubkey_address", "Unknown")
    value = vout.get("value", 0) / 100_000_000
    total_out += value

    print(f"  {addr}  <--  {value:.8f} BTC")

print(f"\nTOTAL OUTPUT BTC: {total_out:.8f}")
print("=" * 100)