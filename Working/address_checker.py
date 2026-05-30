import streamlit as st
import requests
import pandas as pd
from datetime import datetime

API_BASE = "https://blockstream.info/api"
SATS_PER_BTC = 100_000_000


def sats_to_btc(sats):
    return sats / SATS_PER_BTC


def get_json(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def get_address_info(address):
    return get_json(f"{API_BASE}/address/{address}")


def get_recent_txs(address, max_txs=10):
    txs = get_json(f"{API_BASE}/address/{address}/txs/chain")
    return txs[:max_txs]


def format_time(tx):
    timestamp = tx.get("status", {}).get("block_time")
    if not timestamp:
        return "Unconfirmed"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def calculate_address_summary(info):
    chain = info["chain_stats"]
    mempool = info["mempool_stats"]

    received_sats = chain["funded_txo_sum"] + mempool["funded_txo_sum"]
    spent_sats = chain["spent_txo_sum"] + mempool["spent_txo_sum"]
    balance_sats = received_sats - spent_sats
    tx_count = chain["tx_count"] + mempool["tx_count"]

    return received_sats, spent_sats, balance_sats, tx_count


def summarise_transaction_for_address(tx, address):
    received = 0
    spent = 0

    for vout in tx.get("vout", []):
        if vout.get("scriptpubkey_address") == address:
            received += vout.get("value", 0)

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout")
        if prevout and prevout.get("scriptpubkey_address") == address:
            spent += prevout.get("value", 0)

    net = received - spent

    return {
        "Transaction ID": tx["txid"],
        "Time": format_time(tx),
        "Received BTC": sats_to_btc(received),
        "Spent BTC": sats_to_btc(spent),
        "Net BTC": sats_to_btc(net),
        "Fee BTC": sats_to_btc(tx.get("fee", 0)),
    }


def build_received_sent_tables(txs, searched_address, max_rows=300):
    received_rows = []
    sent_rows = []

    for tx in txs:
        txid_short = tx["txid"][:10] + "..."
        tx_time = format_time(tx)

        amount_received_by_searched = 0
        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") == searched_address:
                amount_received_by_searched += vout.get("value", 0)

        amount_spent_by_searched = 0
        for vin in tx.get("vin", []):
            prevout = vin.get("prevout")
            if prevout and prevout.get("scriptpubkey_address") == searched_address:
                amount_spent_by_searched += prevout.get("value", 0)

        if amount_received_by_searched > 0:
            source_addresses = []

            for vin in tx.get("vin", []):
                prevout = vin.get("prevout")
                if not prevout:
                    continue

                from_address = prevout.get("scriptpubkey_address")
                if from_address and from_address != searched_address:
                    source_addresses.append(from_address)

            source_addresses = list(dict.fromkeys(source_addresses))

            if not source_addresses:
                source_addresses = ["Unknown or coinbase transaction"]

            for source in source_addresses:
                received_rows.append({
                    "Transaction": txid_short,
                    "Time": tx_time,
                    "From": source,
                    "Amount Received BTC": sats_to_btc(amount_received_by_searched)
                })

        if amount_spent_by_searched > 0:
            for vout in tx.get("vout", []):
                to_address = vout.get("scriptpubkey_address")
                value = vout.get("value", 0)

                if not to_address:
                    continue

                if to_address == searched_address:
                    continue

                sent_rows.append({
                    "Transaction": txid_short,
                    "Time": tx_time,
                    "To": to_address,
                    "Amount Sent BTC": sats_to_btc(value)
                })

    received_df = pd.DataFrame(received_rows)
    sent_df = pd.DataFrame(sent_rows)

    if len(received_df) > max_rows:
        received_df = received_df.head(max_rows)

    if len(sent_df) > max_rows:
        sent_df = sent_df.head(max_rows)

    return received_df, sent_df


st.title("Address Summary")

st.write(
    "Enter a Bitcoin address to view basic stats, recent transactions, "
    "Bitcoin received and Bitcoin sent."
)

address = st.text_input("Bitcoin address")

max_txs_to_fetch = st.slider(
    "Number of recent transactions to analyse",
    min_value=1,
    max_value=25,
    value=10
)

if address:
    try:
        with st.spinner("Fetching address data..."):
            info = get_address_info(address)
            txs = get_recent_txs(address, max_txs=max_txs_to_fetch)

        received_sats, spent_sats, balance_sats, tx_count = calculate_address_summary(info)

        st.subheader("Basic Address Stats")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Received", f"{sats_to_btc(received_sats):.8f} BTC")
        col2.metric("Spent", f"{sats_to_btc(spent_sats):.8f} BTC")
        col3.metric("Balance", f"{sats_to_btc(balance_sats):.8f} BTC")
        col4.metric("Tx Count", tx_count)

        if tx_count > 1000:
            st.warning(
                "This address has very high activity. "
                "The app will simplify tables so it does not slow down."
            )

        if not txs:
            st.info("No confirmed transactions found for this address yet.")
            st.stop()

        st.subheader("Recent Transactions")

        tx_summary_rows = [summarise_transaction_for_address(tx, address) for tx in txs]
        tx_df = pd.DataFrame(tx_summary_rows)

        st.dataframe(tx_df, use_container_width=True, hide_index=True)

        received_df, sent_df = build_received_sent_tables(txs, address)

        st.subheader("Bitcoin Received By This Address")
        st.write("These rows show recent transactions where the searched address received Bitcoin.")

        if received_df.empty:
            st.info("No received Bitcoin found in the recent transactions analysed.")
        else:
            st.dataframe(received_df, use_container_width=True, hide_index=True)

        st.subheader("Bitcoin Sent From This Address")
        st.write(
            "These rows show recent transactions where the searched address sent Bitcoin to other addresses. "
            "Change sent back to the same searched address is hidden to keep this beginner-friendly."
        )

        if sent_df.empty:
            st.info("No sent Bitcoin found in the recent transactions analysed.")
        else:
            st.dataframe(sent_df, use_container_width=True, hide_index=True)

    except requests.exceptions.HTTPError:
        st.error("Could not fetch this address. Please check the BTC address and try again.")

    except requests.exceptions.Timeout:
        st.error("The request timed out. Try again, or reduce the number of transactions.")

    except requests.exceptions.ConnectionError:
        st.error("Network connection issue. Please check your internet connection and try again.")

    except Exception as e:
        st.error(f"Something went wrong: {e}")
