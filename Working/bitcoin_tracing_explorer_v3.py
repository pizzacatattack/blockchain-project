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
PRICE_API = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=aud"
SATS_PER_BTC = 100_000_000
PAGE_SIZE = 25


# -----------------------------
# Helper functions
# -----------------------------
def sats_to_btc(sats):
    """Convert satoshis to BTC."""
    return sats / SATS_PER_BTC


def btc_to_aud(btc, btc_aud_rate):
    """Convert BTC to AUD using the current BTC/AUD rate."""
    if btc_aud_rate is None:
        return None
    return btc * btc_aud_rate


def format_btc(value):
    """Format a BTC amount neatly."""
    return f"{value:,.8f} BTC"


def format_aud(value):
    """Format an AUD amount neatly."""
    if value is None:
        return "AUD unavailable"
    return f"A${value:,.2f}"


def format_sats(sats):
    """Format satoshis neatly."""
    return f"{sats:,} sats"


def short_txid(txid):
    """Shorten a transaction ID for table display."""
    if not txid:
        return "Unknown"
    return txid[:8] + "..." + txid[-6:]


def short_address(address):
    """Shorten a Bitcoin address for table display."""
    if not address:
        return "Unknown"
    if len(address) <= 18:
        return address
    return address[:10] + "..." + address[-8:]


def get_json(url):
    """Fetch JSON data from an API URL."""
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=300)
def get_btc_aud_rate():
    """Fetch the current BTC to AUD price.

    Cached for 5 minutes so the app does not call the price API on every rerun.
    """
    try:
        data = get_json(PRICE_API)
        return data.get("bitcoin", {}).get("aud")
    except Exception:
        return None


def get_address_info(address):
    """Fetch summary information for a Bitcoin address."""
    return get_json(f"{API_BASE}/address/{address}")


def get_address_txs_page(address, last_seen_txid=None):
    """Fetch one page of confirmed transactions for a Bitcoin address.

    Blockstream returns up to 25 transactions per page.
    If last_seen_txid is provided, it fetches the next older page.
    """
    if last_seen_txid:
        return get_json(f"{API_BASE}/address/{address}/txs/chain/{last_seen_txid}")
    return get_json(f"{API_BASE}/address/{address}/txs/chain")


def get_transaction(txid):
    """Fetch a single transaction by transaction ID."""
    return get_json(f"{API_BASE}/tx/{txid}")


def format_time_from_timestamp(timestamp):
    """Format a Unix timestamp into a readable date/time."""
    if not timestamp:
        return "Unconfirmed"
    return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC")


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


def calculate_address_amounts_in_tx(tx, searched_address):
    """Calculate how much the searched address received and spent in one transaction."""
    received_sats = 0
    spent_sats = 0

    for vout in tx.get("vout", []):
        if vout.get("scriptpubkey_address") == searched_address:
            received_sats += vout.get("value", 0)

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout")
        if prevout and prevout.get("scriptpubkey_address") == searched_address:
            spent_sats += prevout.get("value", 0)

    net_sats = received_sats - spent_sats
    return received_sats, spent_sats, net_sats


def describe_direction(received_sats, spent_sats, net_sats):
    """Describe the transaction from the searched address perspective."""
    if received_sats > 0 and spent_sats == 0:
        return "Incoming"
    if spent_sats > 0 and received_sats == 0:
        return "Outgoing"
    if spent_sats > 0 and received_sats > 0:
        if net_sats > 0:
            return "Mixed / net received"
        if net_sats < 0:
            return "Mixed / net spent"
        return "Mixed / no net change"
    return "Related"


def build_recent_transaction_table(txs, searched_address, btc_aud_rate):
    """Build an explorer-style recent transaction summary table."""
    rows = []

    for tx in txs:
        received_sats, spent_sats, net_sats = calculate_address_amounts_in_tx(tx, searched_address)
        total_input_sats, total_output_sats, fee_sats = calculate_transaction_totals(tx)

        received_btc = sats_to_btc(received_sats)
        spent_btc = sats_to_btc(spent_sats)
        net_btc = sats_to_btc(net_sats)
        fee_btc = sats_to_btc(fee_sats)
        total_output_btc = sats_to_btc(total_output_sats)

        rows.append({
            "Transaction": short_txid(tx.get("txid")),
            "Time": format_time(tx),
            "Direction": describe_direction(received_sats, spent_sats, net_sats),
            "Inputs": len(tx.get("vin", [])),
            "Outputs": len(tx.get("vout", [])),
            "Received BTC": received_btc,
            "Received AUD": btc_to_aud(received_btc, btc_aud_rate),
            "Spent BTC": spent_btc,
            "Spent AUD": btc_to_aud(spent_btc, btc_aud_rate),
            "Net BTC": net_btc,
            "Net AUD": btc_to_aud(net_btc, btc_aud_rate),
            "Tx Output Total BTC": total_output_btc,
            "Tx Output Total AUD": btc_to_aud(total_output_btc, btc_aud_rate),
            "Fee BTC": fee_btc,
            "Fee AUD": btc_to_aud(fee_btc, btc_aud_rate),
            "Full TXID": tx.get("txid")
        })

    return pd.DataFrame(rows)


def build_received_sent_tables(txs, searched_address, btc_aud_rate, max_rows=500):
    """Build beginner-friendly received and sent tables."""
    received_rows = []
    sent_rows = []

    for tx in txs:
        txid_short = short_txid(tx.get("txid"))
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

            amount_btc = sats_to_btc(amount_received_by_searched)

            for source in source_addresses:
                received_rows.append({
                    "Transaction": txid_short,
                    "Time": tx_time,
                    "From": source,
                    "Amount Received BTC": amount_btc,
                    "Amount Received AUD": btc_to_aud(amount_btc, btc_aud_rate)
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

                amount_btc = sats_to_btc(value)

                sent_rows.append({
                    "Transaction": txid_short,
                    "Time": tx_time,
                    "To": to_address,
                    "Amount Sent BTC": amount_btc,
                    "Amount Sent AUD": btc_to_aud(amount_btc, btc_aud_rate)
                })

    received_df = pd.DataFrame(received_rows)
    sent_df = pd.DataFrame(sent_rows)

    if len(received_df) > max_rows:
        received_df = received_df.head(max_rows)

    if len(sent_df) > max_rows:
        sent_df = sent_df.head(max_rows)

    return received_df, sent_df


def build_transaction_input_output_tables(tx, btc_aud_rate):
    """Build input and output tables for a transaction lookup."""
    input_rows = []
    output_rows = []

    for index, vin in enumerate(tx.get("vin", []), start=1):
        prevout = vin.get("prevout")

        if prevout:
            amount_btc = sats_to_btc(prevout.get("value", 0))
            full_address = prevout.get("scriptpubkey_address", "Unknown")

            input_rows.append({
                "Input #": index,
                "From Address": full_address,
                "Short Address": short_address(full_address),
                "Amount BTC": amount_btc,
                "Amount AUD": btc_to_aud(amount_btc, btc_aud_rate)
            })
        else:
            input_rows.append({
                "Input #": index,
                "From Address": "Unknown or coinbase input",
                "Short Address": "Unknown",
                "Amount BTC": 0,
                "Amount AUD": btc_to_aud(0, btc_aud_rate)
            })

    for index, vout in enumerate(tx.get("vout", []), start=1):
        amount_btc = sats_to_btc(vout.get("value", 0))
        full_address = vout.get("scriptpubkey_address", "Unknown")

        output_rows.append({
            "Output #": index,
            "To Address": full_address,
            "Short Address": short_address(full_address),
            "Amount BTC": amount_btc,
            "Amount AUD": btc_to_aud(amount_btc, btc_aud_rate)
        })

    return pd.DataFrame(input_rows), pd.DataFrame(output_rows)


def display_dataframe(df):
    """Display a dataframe with consistent formatting."""
    if df.empty:
        st.info("No rows to show.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Received BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Spent BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Net BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Tx Output Total BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Fee BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount Received BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount Sent BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Received AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Spent AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Net AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Tx Output Total AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Fee AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Amount Received AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Amount Sent AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Amount AUD": st.column_config.NumberColumn(format="A$%,.2f"),
        }
    )


def reset_address_state(address):
    """Reset transaction pagination when the searched address changes."""
    st.session_state.current_address = address
    st.session_state.loaded_txs = []
    st.session_state.last_seen_txid = None
    st.session_state.no_more_txs = False


def load_next_page(address):
    """Load the next page of address transactions into session state."""
    last_seen_txid = st.session_state.get("last_seen_txid")
    new_txs = get_address_txs_page(address, last_seen_txid)

    if not new_txs:
        st.session_state.no_more_txs = True
        return

    existing_txids = {tx.get("txid") for tx in st.session_state.loaded_txs}
    unique_new_txs = [tx for tx in new_txs if tx.get("txid") not in existing_txids]

    st.session_state.loaded_txs.extend(unique_new_txs)
    st.session_state.last_seen_txid = new_txs[-1].get("txid")

    if len(new_txs) < PAGE_SIZE:
        st.session_state.no_more_txs = True


# -----------------------------
# Main app
# -----------------------------
st.title("₿ Bitcoin Tracing Explorer")

st.write(
    "A beginner-friendly Bitcoin lookup tool for viewing address activity "
    "and checking individual transactions."
)

btc_aud_rate = get_btc_aud_rate()

if btc_aud_rate:
    st.caption(f"Current estimate: 1 BTC ≈ {format_aud(btc_aud_rate)}. AUD values are estimates only.")
else:
    st.warning("BTC/AUD price could not be loaded, so AUD estimates may be unavailable.")

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

    address = st.text_input("Bitcoin address", key="address_input").strip()

    if address:
        try:
            if st.session_state.get("current_address") != address:
                reset_address_state(address)

            with st.spinner("Fetching address data..."):
                info = get_address_info(address)

                # Load the first page automatically.
                if not st.session_state.loaded_txs:
                    load_next_page(address)

            txs = st.session_state.loaded_txs
            received_sats, spent_sats, balance_sats, tx_count = calculate_address_summary(info)

            st.divider()
            st.subheader("Basic Address Stats")

            received_btc = sats_to_btc(received_sats)
            spent_btc = sats_to_btc(spent_sats)
            balance_btc = sats_to_btc(balance_sats)

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Received", format_btc(received_btc), format_aud(btc_to_aud(received_btc, btc_aud_rate)))
            col2.metric("Spent", format_btc(spent_btc), format_aud(btc_to_aud(spent_btc, btc_aud_rate)))
            col3.metric("Balance", format_btc(balance_btc), format_aud(btc_to_aud(balance_btc, btc_aud_rate)))
            col4.metric("Tx Count", tx_count)

            if tx_count > 1000:
                st.warning(
                    "This address has very high activity. "
                    "The app loads transactions one page at a time so it does not slow down."
                )

            if not txs:
                st.info("No confirmed transactions found for this address yet.")
                st.stop()

            st.divider()
            st.subheader("Recent Transactions")

            st.write(
                f"Showing {len(txs)} loaded transaction(s). "
                "Use the button below to load older transactions, 25 at a time."
            )

            with st.expander("What does this table mean?"):
                st.write(
                    "This table summarises recent transactions involving the searched address. "
                    "The Inputs and Outputs columns show the structure of the whole transaction. "
                    "Many inputs and many outputs can sometimes be interesting for blockchain analysis, "
                    "because it may suggest exchange activity, consolidation, fan-out behaviour or possible mixing patterns."
                )
                st.write(
                    "Received, Spent and Net are calculated from the searched address perspective. "
                    "The full transaction can include many other addresses."
                )

            tx_df = build_recent_transaction_table(txs, address, btc_aud_rate)
            display_dataframe(tx_df)

            load_col, reset_col = st.columns([1, 4])

            with load_col:
                if st.button("Load next 25", disabled=st.session_state.no_more_txs):
                    with st.spinner("Loading older transactions..."):
                        load_next_page(address)
                    st.rerun()

            with reset_col:
                if st.session_state.no_more_txs:
                    st.caption("No more confirmed transactions were returned by the API.")
                else:
                    st.caption("This keeps the app fast and avoids loading a huge address history all at once.")

            received_df, sent_df = build_received_sent_tables(txs, address, btc_aud_rate)

            st.divider()
            st.subheader("Bitcoin Received By This Address")
            st.write("These rows show loaded transactions where the searched address received Bitcoin.")

            if received_df.empty:
                st.info("No received Bitcoin found in the loaded transactions.")
            else:
                display_dataframe(received_df)

            st.divider()
            st.subheader("Bitcoin Sent From This Address")
            st.write(
                "These rows show loaded transactions where the searched address sent Bitcoin to other addresses. "
                "Change sent back to the same searched address is hidden to keep this beginner-friendly."
            )

            if sent_df.empty:
                st.info("No sent Bitcoin found in the loaded transactions.")
            else:
                display_dataframe(sent_df)

        except requests.exceptions.HTTPError:
            st.error("Could not fetch this address. Please check the Bitcoin address and try again.")

        except requests.exceptions.Timeout:
            st.error("The request timed out. Try again shortly.")

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

    txid = st.text_input("Transaction ID", key="txid_input").strip()

    if txid:
        try:
            with st.spinner("Fetching transaction data..."):
                tx = get_transaction(txid)

            status = tx.get("status", {})
            confirmed = status.get("confirmed", False)
            block_time = status.get("block_time")

            total_input_sats, total_output_sats, fee_sats = calculate_transaction_totals(tx)
            input_df, output_df = build_transaction_input_output_tables(tx, btc_aud_rate)

            total_input_btc = sats_to_btc(total_input_sats)
            total_output_btc = sats_to_btc(total_output_sats)
            fee_btc = sats_to_btc(fee_sats)

            st.divider()
            st.subheader("Transaction Summary")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Status", "Confirmed" if confirmed else "Unconfirmed")
            col2.metric("Time", format_time_from_timestamp(block_time))
            col3.metric("Inputs", len(tx.get("vin", [])))
            col4.metric("Outputs", len(tx.get("vout", [])))

            col5, col6, col7 = st.columns(3)

            col5.metric("Total Input", format_btc(total_input_btc), format_aud(btc_to_aud(total_input_btc, btc_aud_rate)))
            col6.metric("Total Output", format_btc(total_output_btc), format_aud(btc_to_aud(total_output_btc, btc_aud_rate)))
            col7.metric("Fee", format_btc(fee_btc), format_aud(btc_to_aud(fee_btc, btc_aud_rate)))

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
                display_dataframe(input_df)

            st.divider()
            st.subheader("Output Addresses")
            st.write("These are the addresses that received Bitcoin from this transaction.")

            if output_df.empty:
                st.info("No output data found for this transaction.")
            else:
                display_dataframe(output_df)

        except requests.exceptions.HTTPError:
            st.error("Could not fetch this transaction. Please check the transaction ID and try again.")

        except requests.exceptions.Timeout:
            st.error("The request timed out. Try again shortly.")

        except requests.exceptions.ConnectionError:
            st.error("Network connection issue. Please check your internet connection and try again.")

        except Exception as e:
            st.error(f"Something went wrong: {e}")
