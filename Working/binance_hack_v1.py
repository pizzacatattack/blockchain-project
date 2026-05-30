"""
Streamlit dashboard for the Binance hack motivating example.

This app turns the plain Python case-study script into an investigator-style
Streamlit dashboard. It starts from a known Bitcoin transaction, summarises the
direct outputs, checks limited downstream activity for mixer-like structure, and
allows a small branch trace from selected addresses.

Important: this is an educational heuristic tool. Scores and labels are signals
for discussion, not proof of identity, intent, or a specific laundering service.
"""

import time
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# CONFIG
# -----------------------------

case_name = "Binance Hack Motivating Example"

KNOWN_HACK_TXID = "e8b406091959700dbffcff30a60b190133721e5c39e89bb5fe23c5a554ab05ea"
DEFAULT_RECOMBINED_ADDRESS = "bc1q2rdpyt8ed9pm56u9t0zjf94zrdu6gufa47pf62"


# -----------------------------
# Helper: convert satoshis to BTC
# -----------------------------

def sats_to_btc(value):
    """Convert satoshis to BTC.

    Args:
        value: Bitcoin value in satoshis, as returned by the Blockstream API.

    Returns:
        The BTC value as a float, or None when the input value is missing.
    """
    return value / 100_000_000 if value is not None else None


# -----------------------------
# Fetch one transaction by TXID
# -----------------------------

@st.cache_data(show_spinner=False)
def get_transaction(txid):
    """Fetch a single Bitcoin transaction from the Blockstream API.

    Args:
        txid: Transaction ID to fetch.

    Returns:
        Raw transaction JSON from Blockstream.
    """

    url = f"https://blockstream.info/api/tx/{txid}"

    res = requests.get(url, timeout=20)
    res.raise_for_status()

    return res.json()



def get_tx_date_from_tx(tx):
    """Return a readable confirmation date from a transaction JSON object."""
    try:
        ts = tx["status"]["block_time"]
        return datetime.utcfromtimestamp(ts).strftime("%d %b %Y")
    except Exception:
        return "Unknown"


def build_direct_flow_table(outputs_df, top_n=8):
    """Build a Locky-style flow table for the largest direct outputs."""
    table = outputs_df.head(top_n).copy()

    rows = []
    for i, row in table.iterrows():
        timestamp = row["Timestamp"]
        rows.append({
            "Step": i + 1,
            "Date": timestamp.strftime("%d %b %Y") if pd.notna(timestamp) else "Unknown",
            "From address": "Known Binance hack transaction",
            "To address": row["Output Address"],
            "BTC moved": f"{row['Output BTC']:.8f} BTC",
            "Interpretation": "Direct output from the initial distribution transaction",
        })

    return pd.DataFrame(rows)


def build_branch_flow_table(branch_df):
    """Convert branch trace output into a beginner-friendly flow table."""
    if branch_df.empty:
        return branch_df

    rows = []
    for _, row in branch_df.iterrows():
        btc_value = row["BTC"]
        rows.append({
            "Hop": row["Hop"],
            "From address": row["From Address"],
            "To address": row["To Address"] if pd.notna(row["To Address"]) else "No onward address above threshold",
            "BTC moved": f"{btc_value:.8f} BTC" if pd.notna(btc_value) else "N/A",
            "Interpretation": row["Interpretation"],
        })

    return pd.DataFrame(rows)


# -----------------------------
# Fetch confirmed transactions for an address
# -----------------------------

@st.cache_data(show_spinner=False)
def get_all_transactions(address, max_pages=None):
    """Fetch confirmed transactions involving an address.

    max_pages limits how many pages are fetched so the app
    does not run forever.

    Args:
        address: Bitcoin address to inspect.
        max_pages: Optional maximum number of Blockstream result pages to fetch.

    Returns:
        A list of confirmed transaction JSON objects involving the address.
    """

    all_txs = []
    last_seen = None
    page_count = 0

    while True:
        # Blockstream paginates address history. The first request has no
        # cursor; later requests use the last transaction ID from the previous
        # page to continue the chain.
        if last_seen:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain"

        for attempt in range(3):
            try:
                res = requests.get(url, timeout=20)
                res.raise_for_status()
                data = res.json()
                break
            except requests.exceptions.RequestException:
                # Network/API calls can fail transiently. Retrying makes the
                # app less brittle without hiding repeated failures.
                time.sleep(2)
        else:
            break

        all_txs.extend(data)

        page_count += 1

        # A cap is useful for case-study exploration because high-activity
        # exchange or service addresses can have very large histories.
        if max_pages is not None and page_count >= max_pages:
            break

        # Blockstream returns 25 transactions per full page. Fewer than 25
        # means there are no more confirmed transactions to fetch.
        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.5)

    return all_txs


# -----------------------------
# Extract outputs from one transaction
# -----------------------------

def extract_transaction_outputs(tx):
    """Convert one transaction's outputs into a readable table.

    Used for the original Binance hack transaction.

    Args:
        tx: Raw transaction JSON.

    Returns:
        DataFrame of direct outputs sorted from largest to smallest BTC amount.
    """

    rows = []

    txid = tx["txid"]
    timestamp = tx["status"].get("block_time")

    for i, vout in enumerate(tx.get("vout", [])):
        value_sats = vout.get("value")
        address = vout.get("scriptpubkey_address")

        rows.append({
            "Transaction ID": txid,
            "Timestamp": pd.to_datetime(timestamp, unit="s", errors="coerce"),
            "Output Index": i,
            "Output Address": address,
            "Output BTC": sats_to_btc(value_sats)
        })

    df = pd.DataFrame(rows)

    return df.sort_values("Output BTC", ascending=False).reset_index(drop=True)


# -----------------------------
# Build outputs table from many transactions
# -----------------------------

def build_transaction_outputs(txs):
    """Convert many transactions into an outputs table.

    Used when following an address after the hack transaction.

    Args:
        txs: List of raw transaction JSON objects.

    Returns:
        DataFrame containing output address, BTC value, timestamp and txid.
    """

    rows = []

    for tx in txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for vout in tx.get("vout", []):
            address = vout.get("scriptpubkey_address")
            value = vout.get("value")

            # Skip non-standard or incomplete outputs that do not expose a
            # normal address/value pair suitable for this simple analysis.
            if address is None or value is None:
                continue

            rows.append({
                "Transaction ID": txid,
                "Timestamp": pd.to_datetime(timestamp, unit="s", errors="coerce"),
                "Output Address": address,
                "BTC": sats_to_btc(value)
            })

    return pd.DataFrame(rows)


# -----------------------------
# Summarise outputs by address
# -----------------------------

def summarise_outputs(df_outputs):
    """Summarise total BTC received by each output address.

    Args:
        df_outputs: DataFrame created by build_transaction_outputs().

    Returns:
        DataFrame grouped by output address and sorted by BTC amount.
    """

    if df_outputs.empty:
        return df_outputs

    summary = (
        df_outputs
        .groupby("Output Address", as_index=False)
        .agg({"BTC": "sum"})
        .sort_values("BTC", ascending=False)
        .reset_index(drop=True)
    )

    return summary


# -----------------------------
# Detect equal-output groups
# -----------------------------

def detect_equal_output_groups(tx, tolerance_sats=1000, min_group_size=3):
    """Detect groups of outputs with the same or near-same value.

    CoinJoin transactions often have many equal-value outputs.

    Args:
        tx: Raw transaction JSON.
        tolerance_sats: Maximum satoshi difference treated as approximately equal.
        min_group_size: Minimum number of near-equal outputs required to form a group.

    Returns:
        A list of equal-output groups. Each group is a list of output dictionaries.
    """

    outputs = []

    for vout in tx.get("vout", []):
        value = vout.get("value")
        address = vout.get("scriptpubkey_address")

        if value is not None and address is not None:
            outputs.append({
                "address": address,
                "value_sats": value,
                "value_btc": sats_to_btc(value)
            })

    groups = []
    used = set()

    for i, output in enumerate(outputs):
        if i in used:
            continue

        group = [output]
        used.add(i)

        for j, other in enumerate(outputs):
            if j in used:
                continue

            # Small tolerance avoids missing near-equal denominations caused by
            # rounding or fee-related dust differences.
            if abs(output["value_sats"] - other["value_sats"]) <= tolerance_sats:
                group.append(other)
                used.add(j)

        if len(group) >= min_group_size:
            groups.append(group)

    return groups


# -----------------------------
# Score transaction for mixer-like structure
# -----------------------------

def score_mixer_transaction(tx):
    """Score a transaction based on mixer/CoinJoin-like structure.

    Higher score = more mixer-like.

    Args:
        tx: Raw transaction JSON.

    Returns:
        Dictionary with transaction metrics, score and plain-English reasons.
    """

    inputs = tx.get("vin", [])
    outputs = tx.get("vout", [])

    input_addresses = set()
    output_addresses = set()

    for vin in inputs:
        prevout = vin.get("prevout", {})
        address = prevout.get("scriptpubkey_address")

        if address:
            input_addresses.add(address)

    for vout in outputs:
        address = vout.get("scriptpubkey_address")

        if address:
            output_addresses.add(address)

    equal_groups = detect_equal_output_groups(tx)

    largest_equal_group = 0

    if equal_groups:
        largest_equal_group = max(len(group) for group in equal_groups)

    score = 0
    reasons = []

    # These weights are intentionally simple. They are designed to make the
    # case study explainable, not to replace professional blockchain analytics.
    if len(inputs) >= 5:
        score += 2
        reasons.append("many inputs")

    if len(outputs) >= 5:
        score += 2
        reasons.append("many outputs")

    if largest_equal_group >= 3:
        score += 3
        reasons.append("repeated equal-sized outputs")

    if len(input_addresses) >= 3:
        score += 1
        reasons.append("multiple input addresses")

    if len(output_addresses) >= 3:
        score += 1
        reasons.append("multiple output addresses")

    return {
        "Transaction ID": tx["txid"],
        "Timestamp": pd.to_datetime(tx["status"].get("block_time"), unit="s", errors="coerce"),
        "Input Count": len(inputs),
        "Output Count": len(outputs),
        "Unique Input Addresses": len(input_addresses),
        "Unique Output Addresses": len(output_addresses),
        "Largest Equal Output Group": largest_equal_group,
        "Mixer Score": score,
        "Reasons": ", ".join(reasons)
    }


# -----------------------------
# Analyse downstream mixer-like activity
# -----------------------------

def analyse_address_after_hack(address, max_pages_per_address):
    """Analyse downstream transactions for one direct hack output address.

    For one output address from the hack transaction:
    - fetch later transactions involving that address
    - score those transactions for mixer-like behaviour

    Args:
        address: Direct output address from the known hack transaction.
        max_pages_per_address: Number of Blockstream pages to fetch.

    Returns:
        DataFrame of scored downstream transactions sorted by strongest signal.
    """

    txs = get_all_transactions(address, max_pages=max_pages_per_address)

    results = []

    for tx in txs:
        results.append(score_mixer_transaction(tx))

    df = pd.DataFrame(results)

    if df.empty:
        return df

    df = df.sort_values(
        by=["Mixer Score", "Largest Equal Output Group"],
        ascending=False
    ).reset_index(drop=True)

    return df


# -----------------------------
# Plot largest hack transaction outputs
# -----------------------------

def plot_hack_outputs(outputs_df):
    """Plot the largest direct outputs from the hack transaction.

    Args:
        outputs_df: DataFrame returned by extract_transaction_outputs().

    Returns:
        Matplotlib figure for Streamlit display.
    """

    top_outputs = outputs_df.head(10).copy()

    fig, ax = plt.subplots(figsize=(12, 6))

    labels = [f"Output {i + 1}" for i in range(len(top_outputs))]

    ax.bar(
        labels,
        top_outputs["Output BTC"]
    )

    ax.set_title("Largest direct outputs from known hack transaction")
    ax.set_xlabel("Largest outputs")
    ax.set_ylabel("BTC")

    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig


# -----------------------------
# Follow one large hack output
# -----------------------------

def follow_hack_output_multi(address, max_hops=2, top_n=2, min_btc=0.01):
    """Follow one hack output with limited branching.

    - max_hops: how deep to go
    - top_n: how many outputs to follow per hop

    Args:
        address: Address to start tracing from.
        max_hops: Maximum number of hops to trace.
        top_n: Number of top outputs to follow from each address.
        min_btc: Minimum BTC threshold for meaningful onward outputs.

    Returns:
        DataFrame showing the limited branch trace.
    """

    current_addresses = [address]
    trace_rows = []

    for hop in range(1, max_hops + 1):
        next_addresses = []

        for addr in current_addresses:
            txs = get_all_transactions(addr, max_pages=2)

            df_outputs = build_transaction_outputs(txs)
            summary = summarise_outputs(df_outputs)

            filtered = summary[
                (summary["BTC"] >= min_btc) &
                (summary["Output Address"] != addr)
            ].reset_index(drop=True)

            if filtered.empty:
                trace_rows.append({
                    "Hop": hop,
                    "From Address": addr,
                    "To Address": None,
                    "BTC": None,
                    "Interpretation": "No meaningful outputs above threshold"
                })
                continue

            # Take top N outputs
            top_outputs = filtered.head(top_n)

            if len(filtered) > 5:
                interpretation = "Heavy distribution stage"
            elif len(filtered) <= 3:
                interpretation = "Limited branching"
            else:
                interpretation = "Moderate distribution"

            for _, row in top_outputs.iterrows():
                next_addresses.append(row["Output Address"])
                trace_rows.append({
                    "Hop": hop,
                    "From Address": addr,
                    "To Address": row["Output Address"],
                    "BTC": row["BTC"],
                    "Interpretation": interpretation
                })

        # Move to next hop
        current_addresses = next_addresses

        if not current_addresses:
            break

    return pd.DataFrame(trace_rows)


def build_hack_summary(outputs_df):
    """Build a compact summary table for the known hack transaction.

    Args:
        outputs_df: DataFrame of direct hack transaction outputs.

    Returns:
        Dictionary of key summary metrics.
    """
    return {
        "Total BTC distributed": round(outputs_df["Output BTC"].sum(), 4),
        "Number of outputs": len(outputs_df),
        "Average output size": round(outputs_df["Output BTC"].mean(), 4),
        "Largest output": round(outputs_df["Output BTC"].max(), 4),
        "Smallest output": round(outputs_df["Output BTC"].min(), 8),
    }


def build_downstream_summary(large_outputs, max_pages_per_address):
    """Score downstream activity for the largest direct hack outputs.

    Args:
        large_outputs: Filtered direct outputs from the hack transaction.
        max_pages_per_address: Number of Blockstream pages to fetch for each address.

    Returns:
        DataFrame containing the best mixer-like signal for each checked address.
    """
    downstream_results = []

    for _, row in large_outputs.head(5).iterrows():
        address = row["Output Address"]

        if pd.isna(address):
            continue

        df = analyse_address_after_hack(address, max_pages_per_address)

        if df.empty:
            continue

        best = df.iloc[0]

        downstream_results.append({
            "Hack Output Address": address,
            "Hack Output BTC": row["Output BTC"],
            "Best Downstream TX": best["Transaction ID"],
            "Best Mixer Score": best["Mixer Score"],
            "Largest Equal Output Group": best["Largest Equal Output Group"],
            "Reasons": best["Reasons"]
        })

    return pd.DataFrame(downstream_results)


def score_label(score):
    """Convert a numeric mixer score into an investigator-friendly label."""
    if score >= 7:
        return "High signal"
    if score >= 4:
        return "Moderate signal"
    if score > 0:
        return "Low signal"
    return "No obvious signal"


# -----------------------------
# STREAMLIT APP
# -----------------------------

st.set_page_config(
    page_title="Binance Hack Educational Case Study",
    page_icon="₿",
    layout="wide",
)

st.title("₿ Binance Hack Educational Case Study")
st.caption("Tracing fund movement from a known hack transaction using public blockchain data and simple investigation heuristics.")

st.markdown(
    """
    ### What this case shows

    This case starts with a Bitcoin transaction identified in published research relating to the 2019 Binance hack.
    Public blockchain data from Blockstream is then used to trace how funds were distributed, followed through selected
    downstream wallets, and checked for patterns that may warrant further investigation.
    """
)

st.info(
    "This is an educational case study. The patterns shown here are investigation signals only. "
    "They do not prove identity, intent, or use of a specific laundering service."
)

try:
    with st.spinner("Loading case study transaction..."):
        hack_tx = get_transaction(KNOWN_HACK_TXID)
        outputs_df = extract_transaction_outputs(hack_tx)
        large_outputs = outputs_df[outputs_df["Output BTC"] >= 0.01].reset_index(drop=True)
        hack_summary = build_hack_summary(outputs_df)

    st.subheader("1. Initial fund distribution")

    st.write(
        "This graph shows the largest direct outputs from the known Binance hack transaction. "
        "Large outputs are useful starting points because they may represent staging or redistribution wallets."
    )

    st.pyplot(plot_hack_outputs(outputs_df))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Transaction date", get_tx_date_from_tx(hack_tx))
    col2.metric("Total BTC distributed", f"{hack_summary['Total BTC distributed']:,} BTC")
    col3.metric("Outputs", f"{hack_summary['Number of outputs']}")
    col4.metric("Largest output", f"{hack_summary['Largest output']:,} BTC")

    st.info(
        "What is happening here? This transaction shows the first visible distribution of funds from the known hack transaction. "
        "The largest outputs are checked first because they carry more value and may reveal later movement."
    )

    st.subheader("2. First distribution table")

    st.write(
        "The table below shows the largest direct outputs in a simple from-to format."
    )

    direct_flow_df = build_direct_flow_table(outputs_df, top_n=8)
    st.dataframe(direct_flow_df, use_container_width=True, hide_index=True)

    with st.expander("Show all direct outputs"):
        st.dataframe(outputs_df, use_container_width=True, hide_index=True)

    st.subheader("3. Example follow-on tracing")

    largest_output_address = outputs_df.iloc[0]["Output Address"]

    st.write(
        "The table below follows a limited branch trace from the largest direct output wallet. "
        "This is not a full forensic trace. It is a small example showing how funds can be followed beyond the first transaction."
    )

    with st.spinner("Following the largest direct output with limited branching..."):
        branch_df = follow_hack_output_multi(
            address=largest_output_address,
            max_hops=2,
            top_n=2,
            min_btc=0.01,
        )

    if branch_df.empty:
        st.warning("No follow-on trace results found.")
    else:
        branch_flow_df = build_branch_flow_table(branch_df)
        st.dataframe(branch_flow_df, use_container_width=True, hide_index=True)

    st.info(
        "Why this matters: blockchain tracing can show where funds move next, but it becomes harder to know who controls later wallets without extra attribution data."
    )

    st.subheader("4. Heuristic check for mixer-like behaviour")

    st.write(
        "This section checks selected downstream transactions for simple structural signals, such as many inputs, many outputs, or repeated equal-sized outputs."
    )

    with st.spinner("Checking downstream transactions for mixer-like patterns..."):
        downstream_df = build_downstream_summary(large_outputs, max_pages_per_address=3)

    if downstream_df.empty:
        st.warning("No strong downstream heuristic signals were identified in this limited search.")
    else:
        downstream_df["Signal Label"] = downstream_df["Best Mixer Score"].apply(score_label)
        st.dataframe(downstream_df, use_container_width=True, hide_index=True)

        best = downstream_df.sort_values("Best Mixer Score", ascending=False).iloc[0]
        st.success(
            f"Strongest signal found: score {best['Best Mixer Score']} "
            f"({score_label(best['Best Mixer Score'])})."
        )

    st.info(
        "What does this mean? Mixer-like signals are clues, not proof. "
        "Transactions with many inputs, many outputs, or repeated equal-sized outputs can be seen in mixers, CoinJoin-style transactions, exchanges, and other high-activity services."
    )

    st.subheader("5. Limitations")

    st.markdown(
        """
        - This analysis uses public blockchain data only.
        - The app follows a limited number of branches so the case stays understandable.
        - Exchange and service activity can sometimes look similar to mixer-like behaviour.
        - Following fund movement is easier than confidently identifying who controls later wallets.
        """
    )

    st.subheader("Method note")

    st.markdown(
        """
        This case study starts with a Bitcoin transaction identified in published research relating to the Binance hack.
        Public blockchain data from **Blockstream** was used to trace related activity.

        Simple heuristics were used to highlight patterns that may be useful investigation leads. These signals support
        analysis, but they should not be treated as proof of identity or intent.
        """
    )

    st.subheader("References")

    with st.expander("Show references and data sources"):
        st.markdown(
            """
            Blockstream. (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/api/

            Binance hack research paper. *(Add your Harvard reference here.)*
            """
        )

except requests.exceptions.RequestException as exc:
    st.error(f"Blockstream request failed: {exc}")
except Exception as exc:
    st.error(f"Something went wrong: {exc}")
