import json
import pandas as pd

# Load ransomware dataset
with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

# Add transaction count column
df["tx_count"] = df["transactions"].apply(len)

# Addresses from the transaction that funded the seed
output_addresses = [
    "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E",
    "12p2CcaDixL2FCMBzxzfMhPwufMohDbTmH"
]

matches = df[df["address"].isin(output_addresses)]

print(matches[["address", "family", "balance", "tx_count"]])

# Search for matches
matches = df[df["address"].isin(output_addresses)]

matched_addresses = set(matches["address"])
all_addresses = set(output_addresses)

missing = all_addresses - matched_addresses

print("Not labelled Locky:")
print(missing)

if matches.empty:
    print("No matches found in Ransomwhere dataset.")
else:
    print(matches[["address", "family", "balance", "tx_count", "balanceUSD"]])