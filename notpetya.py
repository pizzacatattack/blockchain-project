import requests
import json
import pandas as pd


#100,000,000 satoshis in a BTC
#funded = outputs sent to an address
#tx_count = total tx connected to address (inputs and outputs)

# Get an address's transactions

#tx_address = "13KBb1G7pkqcJcxpRHg387roBj2NX7Ufyf" #notpetya - 8tx

# tx_address = "1Mz7153HMuxXTuR2R1t78mGSdzaAtNbBWX" #not petya 136tx

# #tx_address = "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq" #colonial pipeline
# tx_url = f"https://blockstream.info/api/address/{tx_address}"
# tx_response = requests.get(tx_url)

# tx_data = tx_response.json()


# print(tx_data)

# print(tx_data.keys())

# # print(tx_data["chain_stats"])

# # print(json.dumps(tx_data["chain_stats"], indent=2)) 

# keys = (tx_data["chain_stats"].keys())

# # print(tx_data["chain_stats"].values())

# dict = (tx_data["chain_stats"])

# for key, value in dict.items() :
#     print (key, value)



# value = dict["funded_txo_count"] 
# print(value)



# df = pd.DataFrame([dict])
# print(df)



# dict2 = (tx_data["mempool_stats"])
# df2 = pd.DataFrame([dict2])
# print(df2)



# Get details for a transaction
# tx_id = "a2a6c377106999c13134004d5b8b1e1dcd32269ad1e347cf38ddca69a95bb531"
# tx_url = f"https://blockstream.info/api/tx/{tx_id}"
# tx_response = requests.get(tx_url)

# tx_data = tx_response.json()

# print(tx_data["fee"])
# print(tx_data["status"])

# print(tx_data.keys())
# # print(tx_data["vin"])
# # print(tx_data["vout"])




btc_addr = "1Mz7153HMuxXTuR2R1t78mGSdzaAtNbBWX" 
btc_addr_url = f"https://blockstream.info/api/address/:address/txs/chain[/:last_seen_txid]"
btc_addr_response = requests.get(btc_addr_url)
btc_addr_data = btc_addr_response.json()

print(btc_addr_data)

