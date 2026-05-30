import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# -----------------------------
# App settings
# -----------------------------
st.set_page_config(
    page_title="₿ Bitcoin Tracing Explorer",
    page_icon="₿",
    layout="wide"
)

API_BASE = "https://blockstream.info/api"
SATS_PER_BTC = 100_000_000


# -----------------------------
# Helper functions
# -----------------------------
def sats_to_btc(sats):
    """Convert satoshis to BTC."""
    return sats / SATS_PER_BTC


def get_json(url):
    """Fetch JSON data from the Blockstream API."""
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def get_address_info(address):
    """Fetch summary information for a Bitcoin address."""
    return get_json(f"{API_BASE}/address/{address}")


def get_recent_txs(address, max_txs=10):
    """Fetch recent confirmed transactions for a Bitcoin address."""
    txs = get_json(f"{API_BASE}/address/{address}/txs/chain")
    return txs[:max_txs]


def get_transaction(txid):
    """Fetch a single transaction by transaction ID."""
    return get_json(f"{API_BASE}/tx/{txid}")


def format_time_from_timestamp(timestamp):
    """Format a Unix timestamp into a readable date/time."""
    if not timestamp:
        return "Unconfirmed"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def format_time(tx):
    """Format the time from a transaction object."""
    timestamp = tx.get("status", {}).get("block_time")
    return format_time_from_timestamp(timestamp)


def calculate_address_summary(info):
    """Calculate total received, spent, balance and transaction count."""
    chain = info["chain_stats"]
    mempool = info["mempool_stats"]

    received_sats = chain["funded_txo_sum"] + mempool["funded_txo_sum"]
    spent_sats = chain["spent_txo_sum"] + mempool["spent_txo_sum"]
    balance_sats = received_sats - spent_sats
    tx_count = chain["tx_count"] + mempool["tx_count"]

    return received_sats, spent_sats, balance_sats, tx_count


def summarise_transaction_for_address(tx, address):
    """Summarise one transaction from the perspective of the searched address."""
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
    """
    Build beginner-friendly received and sent tables.

    Received table:
    - Shows transactions where the searched address received BTC.
    - Uses input addresses as likely sources.

    Sent table:
    - Shows transactions where the searched address spent BTC.
    - Hides change sent back to the same searched address.
    """
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

                # Hide change back to the searched address.
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


def build_transaction_input_output_tables(tx):
    """Build input and output tables for a transaction lookup."""
    input_rows = []
    output_rows = []

    for index, vin in enumerate(tx.get("vin", []), start=1):
        prevout = vin.get("prevout")

        if prevout:
            input_rows.append({
                "Input #": index,
                "From Address": prevout.get("scriptpubkey_address", "Unknown"),
                "Amount BTC": sats_to_btc(prevout.get("value", 0))
            })
        else:
            input_rows.append({
                "Input #": index,
                "From Address": "Unknown or coinbase input",
                "Amount BTC": 0
            })

    for index, vout in enumerate(tx.get("vout", []), start=1):
        output_rows.append({
            "Output #": index,
            "To Address": vout.get("scriptpubkey_address", "Unknown"),
            "Amount BTC": sats_to_btc(vout.get("value", 0))
        })

    return pd.DataFrame(input_rows), pd.DataFrame(output_rows)


def calculate_transaction_totals(tx):
    """Calculate transaction input total, output total and fee."""
    total_input_sats = 0

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout")
        if prevout:
            total_input_sats += prevout.get("value", 0)

    total_output_sats = 0

    for vout in tx.get("vout", []):
        total_output_sats += vout.get("value", 0)

    fee_sats = tx.get("fee", 0)

    return total_input_sats, total_output_sats, fee_sats


# -----------------------------
# Main app
# -----------------------------
st.title("₿ Bitcoin Tracing Explorer")

st.write(
    "A beginner-friendly Bitcoin lookup tool for viewing address activity "
    "and checking individual transactions."
)

st.info(
    "Tip: Start with an address summary to understand the overall activity, "
    "then use the transaction lookup tab to inspect a specific transaction in more detail."
)

tab_address, tab_transaction = st.tabs(["Address Summary", "Transaction Lookup"])


# -----------------------------
# Tab 1: Address Summary
# -----------------------------
with tab_address:
    st.header("Address Summary")

    st.write(
        "Enter a Bitcoin address to view basic stats, recent transactions, "
        "Bitcoin received and Bitcoin sent."
    )

    address = st.text_input("Bitcoin address", key="address_input")

    max_txs_to_fetch = st.slider(
        "Number of recent transactions to analyse",
        min_value=1,
        max_value=25,
        value=10,
        key="address_tx_slider"
    )

    if address:
        try:
            with st.spinner("Fetching address data..."):
                info = get_address_info(address)
                txs = get_recent_txs(address, max_txs=max_txs_to_fetch)

            received_sats, spent_sats, balance_sats, tx_count = calculate_address_summary(info)

            st.divider()
            st.subheader("Basic Address Stats")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Received", f"{sats_to_btc(received_sats):.8f} BTC")
            col2.metric("Spent", f"{sats_to_btc(spent_sats):.8f} BTC")
            col3.metric("Balance", f"{sats_to_btc(balance_sats):.8f} BTC")
            col4.metric("Tx Count", tx_count)

            if tx_count > 1000:
                st.warning(
                    "This address has very high activity. "
                    "The app will only show a simplified recent-transaction view so it does not slow down."
                )

            if not txs:
                st.info("No confirmed transactions found for this address yet.")
                st.stop()

            st.divider()
            st.subheader("Recent Transactions")

            with st.expander("What does this table mean?"):
                st.write(
                    "This table shows recent transactions involving the searched address. "
                    "Received BTC means the searched address received Bitcoin in that transaction. "
                    "Spent BTC means the searched address spent Bitcoin in that transaction. "
                    "Net BTC is received minus spent."
                )

            tx_summary_rows = [summarise_transaction_for_address(tx, address) for tx in txs]
            tx_df = pd.DataFrame(tx_summary_rows)

            st.dataframe(tx_df, use_container_width=True, hide_index=True)

            received_df, sent_df = build_received_sent_tables(txs, address)

            st.divider()
            st.subheader("Bitcoin Received By This Address")
            st.write("These rows show recent transactions where the searched address received Bitcoin.")

            if received_df.empty:
                st.info("No received Bitcoin found in the recent transactions analysed.")
            else:
                st.dataframe(received_df, use_container_width=True, hide_index=True)

            st.divider()
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
            st.error("Could not fetch this address. Please check the Bitcoin address and try again.")

        except requests.exceptions.Timeout:
            st.error("The request timed out. Try again, or reduce the number of transactions.")

        except requests.exceptions.ConnectionError:
            st.error("Network connection issue. Please check your internet connection and try again.")

        except Exception as e:
            st.error(f"Something went wrong: {e}")


# -----------------------------
# Tab 2: Transaction Lookup
# -----------------------------
with tab_transaction:
    st.header("Transaction Lookup")

    st.write(
        "Enter a Bitcoin transaction ID to view the transaction fee, inputs and outputs."
    )

    txid = st.text_input("Transaction ID", key="txid_input")

    if txid:
        try:
            with st.spinner("Fetching transaction data..."):
                tx = get_transaction(txid)

            status = tx.get("status", {})
            confirmed = status.get("confirmed", False)
            block_time = status.get("block_time")

            total_input_sats, total_output_sats, fee_sats = calculate_transaction_totals(tx)
            input_df, output_df = build_transaction_input_output_tables(tx)

            st.divider()
            st.subheader("Transaction Summary")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Status", "Confirmed" if confirmed else "Unconfirmed")
            col2.metric("Time", format_time_from_timestamp(block_time))
            col3.metric("Fee", f"{sats_to_btc(fee_sats):.8f} BTC")
            col4.metric("Outputs", len(tx.get("vout", [])))

            col5, col6, col7 = st.columns(3)

            col5.metric("Total Input", f"{sats_to_btc(total_input_sats):.8f} BTC")
            col6.metric("Total Output", f"{sats_to_btc(total_output_sats):.8f} BTC")
            col7.metric("Inputs", len(tx.get("vin", [])))

            st.info(
                "In most normal Bitcoin transactions, total input is slightly higher than total output. "
                "The difference is the transaction fee paid to miners."
            )

            st.divider()
            st.subheader("Input Addresses")
            st.write("These are the addresses or previous outputs that funded this transaction.")

            if input_df.empty:
                st.info("No input data found for this transaction.")
            else:
                st.dataframe(input_df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Output Addresses")
            st.write("These are the addresses that received Bitcoin from this transaction.")

            if output_df.empty:
                st.info("No output data found for this transaction.")
            else:
                st.dataframe(output_df, use_container_width=True, hide_index=True)

        except requests.exceptions.HTTPError:
            st.error("Could not fetch this transaction. Please check the transaction ID and try again.")

        except requests.exceptions.Timeout:
            st.error("The request timed out. Try again shortly.")

        except requests.exceptions.ConnectionError:
            st.error("Network connection issue. Please check your internet connection and try again.")

        except Exception as e:
            st.error(f"Something went wrong: {e}")
