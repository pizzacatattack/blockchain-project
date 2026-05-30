import streamlit as st
import requests
import pandas as pd
from datetime import datetime


# -----------------------------
# App settings
# -----------------------------
st.set_page_config(
    page_title="Blockchain Hide and Seek",
    page_icon="₿",
    layout="wide"
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .case-card {
        border: 1px solid rgba(120, 120, 120, 0.25);
        border-radius: 18px;
        padding: 1rem 1.2rem;
        background: rgba(250, 250, 250, 0.04);
        margin-bottom: 1rem;
    }
    .small-note {font-size: 0.92rem; color: #666;}
    </style>
    """,
    unsafe_allow_html=True,
)

API_BASE = "https://blockstream.info/api"
PRICE_API = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=aud"
SATS_PER_BTC = 100_000_000
PAGE_SIZE = 25


CASE_STUDIES = {
    "Select a sample case study...": None,
    "CryptoLocker ransomware (high transaction activity)": {
        "address": "1LXrSb67EaH1LGc6d6kWHq8rgv4ZBQAcpU",
        "summary": "CryptoLocker helped introduce Bitcoin to the world of ransomware. With plenty of transaction activity to explore, this address is a good place to start learning how to follow the money.",
        "look_for": [
            "lots of incoming payments",
            "repeated transaction patterns",
            "where the Bitcoin moves next",
            "whether funds appear to be consolidated or redistributed"
        ]
    },
    "Colonial Pipeline / DarkSide (cash-out wallet)": {
        "address": "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq",
        "summary": "The Colonial Pipeline ransomware attack brought cryptocurrency crime into the global spotlight. The ransom payment was easy to spot. Following the money afterwards is where the real game of hide and seek begins.",       
        "look_for": [
            "large value transfers",
            "the first steps in the money trail",
            "where investigators would look next",
            "whether the funds appear to be trying to disappear"
        ]
    },
    "Locky ransomware (sample address)": {
        "address": "178HGmCfR26dSSiFxJQah1U588p2CjgX7f",
        "summary": 
            "Locky was one of the biggest ransomware families of its time. This address is associated with the Locky ecosystem and can be used to explore how investigators use clustering techniques to identify addresses that may belong to the same entity.",
        "look_for": [
            "addresses being used together in transactions",
            "possible clustering behaviour",
            "where the money moves next"
        ]
    },
    "Conti ransomware (large cash-out wallet)": {
        "address": "19iqYbeATe4RxghQZJnYVFU4mjUUu76EA6",
        "summary": "Conti was one of the most prolific ransomware groups in the world. This address has been linked to a suspected peel chain, making it a useful example of how criminals attempt to 'ghost' their funds by repeatedly moving them between addresses.",
        "look_for": [
            "small amounts being 'peeled' off",
            "the remaining balance moving forward",
            "a possible peel chain pattern"
        ]
    },
    "Binance hack (downstream recombination wallet)": {
        "address": "bc1q2rdpyt8ed9pm56u9t0zjf94zrdu6gufa47pf62",
        "summary": "This case study follows Bitcoin linked to the Binance hack. The initial theft was easy to identify, but the real challenge begins afterwards as the funds are moved, split and redistributed. Can you still follow the money?",
        "look_for": [
            "where the stolen Bitcoin moves next",
            "funds being split across multiple addresses",
            "funds being recombined later",
            "whether the trail starts to go cold"
        ]
    },
    "ChipMixer infrastructure (many inputs and outputs)": {
        "address": "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew",
        "summary": "ChipMixer was a cryptocurrency mixer designed to make tracing more difficult. By pooling funds from many users and breaking them into smaller outputs, it attempted to hide the link between senders and receivers.",
        "look_for": [
            "lots of inputs",
            "lots of outputs",
            "repeated small output amounts",
            "transactions that do not pass the vibe check"
        ]
    }
}


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
    """Shorten a transaction ID when a compact display is specifically needed."""
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
            "Transaction ID": tx.get("txid"),
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
            "Fee AUD": btc_to_aud(fee_btc, btc_aud_rate)
        })

    return pd.DataFrame(rows)


def build_received_sent_tables(txs, searched_address, btc_aud_rate, max_rows=500):
    """Build received/sent tables.

    received_summary_df has one row per transaction.
    received_detail_df has one row per contributing source address.
    sent_df has one row per destination output.
    """
    received_summary_rows = []
    received_detail_rows = []
    sent_rows = []

    for tx in txs:
        txid_value = tx.get("txid")
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

            source_count = len(source_addresses)
            amount_btc = sats_to_btc(amount_received_by_searched)
            amount_aud = btc_to_aud(amount_btc, btc_aud_rate)

            received_summary_rows.append({
                "Transaction ID": txid_value,
                "Time": tx_time,
                "Source Address Count": source_count,
                "Total Received BTC": amount_btc,
                "Total Received AUD": amount_aud
            })

            for source in source_addresses:
                received_detail_rows.append({
                    "Transaction ID": txid_value,
                    "Time": tx_time,
                    "Contributing Source Address": source,
                    "Source Address Count": source_count,
                    "Total Received in Transaction BTC": amount_btc,
                    "Total Received in Transaction AUD": amount_aud
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
                    "Transaction ID": txid_value,
                    "Time": tx_time,
                    "To": to_address,
                    "Amount Sent BTC": amount_btc,
                    "Amount Sent AUD": btc_to_aud(amount_btc, btc_aud_rate)
                })

    received_summary_df = pd.DataFrame(received_summary_rows)
    received_detail_df = pd.DataFrame(received_detail_rows)
    sent_df = pd.DataFrame(sent_rows)

    if len(received_summary_df) > max_rows:
        received_summary_df = received_summary_df.head(max_rows)

    if len(received_detail_df) > max_rows:
        received_detail_df = received_detail_df.head(max_rows)

    if len(sent_df) > max_rows:
        sent_df = sent_df.head(max_rows)

    return received_summary_df, received_detail_df, sent_df


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
            "Total Received BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Spent BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Net BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Tx Output Total BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Fee BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount Received BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Total Received in Transaction BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount Sent BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Amount BTC": st.column_config.NumberColumn(format="%,.8f"),
            "Received AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Total Received AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Spent AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Net AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Tx Output Total AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Fee AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Amount Received AUD": st.column_config.NumberColumn(format="A$%,.2f"),
            "Total Received in Transaction AUD": st.column_config.NumberColumn(format="A$%,.2f"),
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


def apply_selected_case_address():
    """Copy a selected case study address into the address input box."""
    selected_case = st.session_state.get("case_study_select")
    case = CASE_STUDIES.get(selected_case)

    if case and case.get("address"):
        st.session_state.address_input = case["address"]


# -----------------------------
# Main app
# -----------------------------
st.title("₿ Blockchain Hide and Seek")
st.caption('A beginner-friendly Bitcoin tracing tool designed to help users "follow the money" on the blockchain.')

btc_aud_rate = get_btc_aud_rate()

if btc_aud_rate:
    st.caption(f"Current estimate: 1 BTC ≈ {format_aud(btc_aud_rate)}. AUD values are estimates only.")
else:
    st.warning("BTC/AUD price could not be loaded, so AUD estimates may be unavailable.")

st.info(
    "Start with an address summary to get the basic picture, "
    "then copy any interesting transaction ID into Transaction Lookup to take a closer look."
)

tab_address, tab_transaction = st.tabs(["Address summary", "Transaction lookup"])


# -----------------------------
# Tab 1: Address Summary
# -----------------------------
with tab_address:
    st.header("Address summary")

    st.write("Choose a sample case study or enter your own Bitcoin address to start following the money.")

    st.subheader("Learn a case from the real world")

    selected_case = st.selectbox(
        "Choose a sample",
        list(CASE_STUDIES.keys()),
        key="case_study_select",
        on_change=apply_selected_case_address
    )

    case = CASE_STUDIES.get(selected_case)

    if case:
        with st.container(border=True):
            st.markdown("**About this case**")
            st.write(case["summary"])

            if case.get("address"):
                st.markdown(f"**Sample address:** `{case['address']}`")
            else:
                st.warning("This sample needs an address added before it can be used.")

            st.markdown("**What to clock**")
            for item in case["look_for"]:
                st.markdown(f"- {item}")

    st.subheader("Or enter your own Bitcoin address")
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
            st.subheader("Basic address stats")

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
                "Load older transactions 25 at a time if you want to keep following the address history."
            )

            with st.expander("What does this table mean?"):
                st.write(
                    "This table shows recent transactions involving the Bitcoin address you entered."
                )

                st.write(
                    "The Inputs and Outputs columns show what happened in the whole transaction, "
                    "not just the address you are investigating. Transactions with lots of inputs or outputs "
                    "can be worth a closer look, as they may suggest consolidation, funds being split apart, "
                    "exchange activity or possible mixing behaviour."
                )

                st.write(
                    "The Received, Spent and Net columns show what happened from the perspective of the address you entered."
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
                    st.caption("This keeps the app fast instead of trying to load a huge address history all at once.")

            received_summary_df, received_detail_df, sent_df = build_received_sent_tables(txs, address, btc_aud_rate)

            st.divider()
            st.subheader("Bitcoin received by this address")
            st.write(
                "These are transactions where the address received Bitcoin. "
                "If the same source address appears repeatedly, it may help show where funds are coming from."
            )

            if received_summary_df.empty:
                st.info("No incoming Bitcoin was found in the loaded transactions.")
            else:
                display_dataframe(received_summary_df)

                with st.expander("Show source addresses"):
                    st.write(
                        "A single transaction can receive Bitcoin from multiple addresses, "
                        "so the same transaction ID may appear more than once in this view."
                    )
                    display_dataframe(received_detail_df)

            st.divider()
            st.subheader("Bitcoin sent by this address")
            st.write(
                "These are transactions where the address helped send Bitcoin. "
                "Some transactions combine funds from multiple addresses, so not all of the Bitcoin shown necessarily belonged to this address."
            )

            st.caption(
                "Want to investigate further? Copy a transaction ID from the table and paste it into Transaction Lookup."
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
    st.header("Transaction lookup")

    st.write(
        "Enter a Bitcoin transaction ID to see what funded the transaction, where the Bitcoin went and how much was paid in fees."
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
            st.subheader("Transaction summary")

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
                "In most Bitcoin transactions, the total input is slightly higher than the total output. "
                "The difference is the transaction fee."
            )

            st.divider()
            st.subheader("Input addresses")
            st.write("These are the addresses or previous outputs that funded this transaction.")

            if input_df.empty:
                st.info("No input data found for this transaction.")
            else:
                display_dataframe(input_df)

            st.divider()
            st.subheader("Output addresses")
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
