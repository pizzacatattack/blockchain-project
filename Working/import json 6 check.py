import json
import pandas as pd

with open(r"C:\Users\hello\streamlit-app\ransomwhere_data.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)
df["tx_count"] = df["transactions"].apply(len)

addresses = [
    "12oDRxwJg2FwM2We8WkKoqJMmq8jYcw2Vk",
    "1GQzjng6yzJLEhZRgsLvWKwvdsE9rqSDHe",
    "1Pu8ighTU2SJ62r2iqfiJ11KKAYGoABX2B",
    "12WzkCue9ADXzKD4WXxQFsCTnv4fomMwfo",
    "13YF7J3xixiT6Lx85shtQdq7Kuf9rEpsfw",
    "1MSApyGxayg8dJ1n3DGAsWeZTwEBpthJZB"
]

matches = df[df["address"].isin(addresses)]

print(matches[["address", "family", "balance", "tx_count"]])

missing = set(addresses) - set(matches["address"])
print("\nNot labelled:")
print(missing)