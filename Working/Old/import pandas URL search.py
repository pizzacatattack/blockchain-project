import pandas as pd
import webbrowser

target = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"

# Check your local Locky dataset
df = pd.read_csv(r"C:\Users\hello\streamlit-app\locky_addresses.csv")

match = df[df["address"] == target]

if match.empty:
    print("Not in Locky CSV")
else:
    print(match)

# Open useful public lookups
urls = [
    f"https://www.walletexplorer.com/address/{target}",
    f"https://www.blockchain.com/explorer/addresses/btc/{target}",
    f"https://www.blockstream.info/address/{target}",
]

for url in urls:
    webbrowser.open(url)