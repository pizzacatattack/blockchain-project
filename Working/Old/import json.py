import json
import pandas as pd

with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)
#address = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"
#match = df[df["address"] == address]
#print(match)

locky = df[df["family"] == "Locky"].copy()

print(len(locky))

print(
    locky[["address", "balance"]]
    .sort_values("balance", ascending=False)
    .head(50)
)

#print(df.head())