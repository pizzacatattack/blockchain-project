#https://pypi.org/project/requests/

#https://blockstream.info/explorer-api
#https://github.com/Blockstream/esplora/blob/master/API.md

#https://www.opensanctions.org/datasets/ransomwhere/

#https://docs.python.org/3/library/json.html

import requests
import json

# Get the current block height
# url = "https://blockstream.info/api/blocks/tip/height"
# response = requests.get(url)
# print(response.text) 

# #Get details for a single transaction
# tx_id = "56a5b477182cddb6edb460b39135a3dc785eaf7ea88a572052a761d6983e26a2"
# tx_url = f"https://blockstream.info/api/tx/{tx_id}"
# tx_response = requests.get(tx_url)
# print(tx_response.json())


# # Get details for a transaction
# tx_id = "56a5b477182cddb6edb460b39135a3dc785eaf7ea88a572052a761d6983e26a2"
# tx_url = f"https://blockstream.info/api/tx/{tx_id}"
# tx_response = requests.get(tx_url)

# tx_data = tx_response.json()

# # print(tx_data["vout"])

# print(tx_data.keys())
# # print(tx_data["vin"])
# # print(tx_data["vout"])


#Get details for an address
tx_address = "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq" 

tx_url = f"https://blockstream.info/api/address/{tx_address}"
tx_response = requests.get(tx_url)

tx_data = tx_response.json()

# print(tx_data["vout"])

print(tx_data.keys())
# print(tx_data["vin"])
# print(tx_data["vout"])







# print(type(tx_data))
# print(len(tx_data))
# print(tx_data[0].keys())

# Get an address's transactions

# tx_address = "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq"
# tx_url = f"https://blockstream.info/api/address/{tx_address}/txs"
# tx_response = requests.get(tx_url)

# tx_data = tx_response.json()

# print(tx_data[0]["txid"]) #prints first transaction



# for tx in tx_data:
#     print(tx["txid"])




# format json output nicer

# tx_address = "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq"
# tx_url = f"https://blockstream.info/api/address/{tx_address}/txs"

# tx_response = requests.get(tx_url)
# tx_data = tx_response.json()

# print(json.dumps(tx_data, indent=2)) 