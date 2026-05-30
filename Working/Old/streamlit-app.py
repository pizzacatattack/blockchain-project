#Blockstream API: https://github.com/Blockstream/esplora/blob/master/API.md
#Streamlit tutorial: https://www.youtube.com/watch?v=d7fnzDQ5qM8&t=1087s
#Streamlit basic concepts: https://docs.streamlit.io/get-started/fundamentals/main-concepts
#Streamlit advanced concepts: https://docs.streamlit.io/get-started/fundamentals/advanced-concepts
#Streamlit create an app: https://docs.streamlit.io/get-started/tutorials/create-an-app
#Streamlit create a multipage app: https://docs.streamlit.io/get-started/tutorials/create-a-multipage-app
#Streamlit app gallery: https://streamlit.io/gallery
#Streamlit documentation: https://docs.streamlit.io/
#to run app - in terminal write: streamlit run streamlit-app.py



import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime


#btc_addr_input = st.text_input("Enter a Bitcoin address: ") #for when I want to create a page that takes a user input



#https://stackoverflow.com/questions/34962104/how-can-i-use-the-apply-function-for-a-single-column
def satoshi_to_btc(satoshi):
    return(satoshi/100000000)


############### Dataframe 1 ###############
############### Bitcoin address stats overview ###############
############### Confirm against blockchain.info ###############

st.write("Locky Example")
st.write("Bitcoin (BTC) address: 178HGmCfR26dSSiFxJQah1U588p2CjgX7f")

#Chain_stats summary table
btc_addr = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"
btc_addr_url = f"https://blockstream.info/api/address/{btc_addr}"
btc_addr_response = requests.get(btc_addr_url)
btc_addr_data = btc_addr_response.json()

#keys = (btc_addr_data["chain_stats"].keys())
chain_stats_dict = (btc_addr_data["chain_stats"])

df = pd.DataFrame([chain_stats_dict])

#Rename DF columns
df.columns = ['Count of Received Tx', 'Received Tx BTC Sum', 'Count of Spent Tx', 'Spent Tx BTC Sum', 'Total Confirmed Tx']

#Create a column derived from two existing columns
df['Unspent BTC Sum'] = df['Received Tx BTC Sum'] - df['Spent Tx BTC Sum']

#Convert transaction sums from satoshi to bitcoin
df['Received Tx BTC Sum'] = df['Received Tx BTC Sum'].apply(satoshi_to_btc)
df['Spent Tx BTC Sum'] = df['Spent Tx BTC Sum'].apply(satoshi_to_btc)
df['Unspent BTC Sum'] = df['Unspent BTC Sum'].apply(satoshi_to_btc)

#Reorder DF columns
df = df[['Total Confirmed Tx', 'Count of Received Tx', 'Received Tx BTC Sum', 'Count of Spent Tx', 'Spent Tx BTC Sum', 'Unspent BTC Sum']]

#Print DF
st.dataframe(df, hide_index=True)


############### Dataframe 2 ###############
############### Bitcoin address most recent 10 transactions ###############
############### Confirm against blockchain.info ###############

st.write("Most recent transactions")
#most recent transactions
btc_addr = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f" 

btc_addr_url = f"https://blockstream.info/api/address/{btc_addr}/txs"
btc_addr_response = requests.get(btc_addr_url)
btc_addr_data = btc_addr_response.json()



#https://www.tutorialspoint.com/article/python-convert-list-of-nested-dictionary-into-pandas-dataframe
rows = []
count = 0
for i in btc_addr_data:
    if count < 140:
        rows.append({
            "txid": i["txid"],
            "block_time": i["status"]["block_time"]
        })
    count += 1

df2 = pd.DataFrame(rows)

df2.insert(0, 'BTC addr', btc_addr) 

df2.columns = ['BTC addr', 'Transaction ID', 'Timestamp']


#https://stackoverflow.com/questions/74495737/how-to-show-first-5-characters-within-a-column-in-python
df2['BTC addr'] = df2['BTC addr'].str[:10] + '...'
df2['Transaction ID'] = df2['Transaction ID'].str[:10] + '...'


#https://datascientyst.com/convert-unix-time-to-date-pandas
df2['Timestamp'] = pd.to_datetime(df2['Timestamp'],unit='s')


st.dataframe(df2)



