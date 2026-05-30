import pandas as pd

df = pd.read_csv(r"C:\Users\hello\streamlit-app\locky_addresses.csv")

input_addresses = [
    "33Ypk7PMwf7pJzTQ4wzgaN27MwHDqMWSpC",
    "37iBN9HDzzU2xcoq8ajLjFostAuDzLY2Ec",
    "33BJxctd6xKj39BHPztyESuexRSKyesY7X",
]

two_tx = df[df["tx_count"] == 2].copy()

# convert satoshis to BTC
two_tx["btc"] = two_tx["balance"] / 100_000_000

# sort biggest first
two_tx = two_tx.sort_values("btc", ascending=False)



print(two_tx[["address", "btc", "tx_count"]].head(50))