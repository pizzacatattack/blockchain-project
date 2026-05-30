import json
import pandas as pd

with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

locky = df[df["family"] == "Locky"].copy()

locky["tx_count"] = locky["transactions"].apply(len)

# seed = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"

candidates = locky[
    (locky["tx_count"] >= 2) &
    (locky["tx_count"] <= 5)
].sort_values(["tx_count", "balance"], ascending=[True, False])

print(candidates[["address", "tx_count", "balance"]].head(50))