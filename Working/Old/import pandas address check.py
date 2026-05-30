import json
import pandas as pd

with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

df["tx_count"] = df["transactions"].apply(len)

target = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"

match = df[df["address"] == target]

if match.empty:
    print("Address not found in Ransomwhere dataset")
else:
    print(match[["address", "family", "balance", "tx_count", "balanceUSD"]])