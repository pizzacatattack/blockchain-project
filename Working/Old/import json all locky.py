import json
import pandas as pd

with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

locky = df[df["family"] == "Locky"].copy()

locky["tx_count"] = locky["transactions"].apply(len)

locky[["address", "balance", "tx_count", "updatedAt", "balanceUSD"]].to_csv(
    r"C:\Users\hello\streamlit-app\locky_addresses.csv",
    index=False
)

print("CSV saved successfully")
print(f"Total Locky addresses: {len(locky)}")