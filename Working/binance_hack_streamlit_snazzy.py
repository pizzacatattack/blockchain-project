import time

import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# CONFIG
# -----------------------------

DEFAULT_CASE_NAME = "Binance Hack Motivating Example"
DEFAULT_HACK_TXID = "e8b406091959700dbffcff30a60b190133721e5c39e89bb5fe23c5a554ab05ea"
DEFAULT_RECOMBINED_ADDRESS = "bc1q2rdpyt8ed9pm56u9t0zjf94zrdu6gufa47pf62"


# -----------------------------
# Helper: convert satoshis to BTC
# -----------------------------

def sats_to_btc(value):
    """
    Convert satoshis to BTC.

    Blockstream returns Bitcoin values in satoshis. Converting to BTC makes
    the Streamlit tables and metrics easier for readers to understand.

    Args:
        value: Bitcoin amount in satoshis.

    Returns:
        Bitcoin amount in BTC, or None when the input value is missing.
    """
    return value / 100_000_000 if value is not None else None


# -----------------------------
# Fetch one transaction by TXID
# -----------------------------

@st.cache_data(show_spinner=False)
def get_transaction(txid):
    """
    Fetch a single Bitcoin transaction from the Blockstream API.

    Streamlit caches the result so rerunning the app does not repeatedly fetch
    the same transaction.

    Args:
        txid: Bitcoin transaction ID.

    Returns:
        Raw transaction JSON returned by Blockstream.
    """
    url = f"https://blockstream.info/api/tx/{txid}"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    return res.json()


# -----------------------------
# Fetch confirmed transactions for an address
# -----------------------------

@st.cache_data(show_spinner=False)
def get_all_transactions(address, max_pages=None):
    """
    Fetch confirmed transactions involving an address.

    Blockstream returns address history in pages. This function follows the
    pagination cursor until there are no more full pages or until max_pages is
    reached.

    Args:
        address: Bitcoin address to inspect.
        max_pages: Optional maximum number of Blockstream pages to fetch.

    Returns:
        List of raw transaction JSON objects.
    """
    all_txs = []
    last_seen = None
    page_count = 0

    while True:
        # Blockstream pagination uses the last transaction ID from the previous page.
        if last_seen:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain"

        # Retry transient network/API failures before giving up on this address.
        for attempt in range(3):
            try:
                res = requests.get(url, timeout=20)
                res.raise_for_status()
                data = res.json()
                break
            except requests.exceptions.RequestException:
                time.sleep(2)
        else:
            break

        all_txs.extend(data)
        page_count += 1

        if max_pages is not None and page_count >= max_pages:
            break

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.5)

    return all_txs


# -----------------------------
# Extract outputs from one transaction
# -----------------------------

def extract_transaction_outputs(tx):
    """
    Convert one transaction's outputs into a readable table.

    Used for the original Binance hack transaction. Sorting by output size helps
    identify the largest direct destinations first.

    Args:
        tx: Raw transaction JSON.

    Returns:
        DataFrame containing one row per output.
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
    """
    Convert many transactions into an outputs table.

    Used when following an address after the hack transaction.

    Args:
        txs: List of raw transaction JSON objects.

    Returns:
        DataFrame of output addresses and BTC values.
    """
    rows = []

    for tx in txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for vout in tx.get("vout", []):
            address = vout.get("scriptpubkey_address")
            value = vout.get("value")

            # Skip outputs that cannot be attributed to a standard address.
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
    """
    Summarise total BTC received by each output address.

    Args:
        df_outputs: DataFrame of transaction outputs.

    Returns:
        DataFrame grouped by output address and sorted by BTC amount.
    """
    if df_outputs.empty:
        return df_outputs

    return (
        df_outputs
        .groupby("Output Address", as_index=False)
        .agg({"BTC": "sum"})
        .sort_values("BTC", ascending=False)
        .reset_index(drop=True)
    )


# -----------------------------
# Detect equal-output groups
# -----------------------------

def detect_equal_output_groups(tx, tolerance_sats=1000, min_group_size=3):
    """
    Detect groups of outputs with the same or near-same value.

    Equal-sized outputs are a common CoinJoin/mixer clue because they make it
    harder to match a specific input to a specific output. The tolerance allows
    for tiny differences caused by fee handling or rounding.

    Args:
        tx: Raw transaction JSON.
        tolerance_sats: Maximum satoshi difference for outputs to count as equal.
        min_group_size: Minimum number of similar outputs needed to flag a group.

    Returns:
        List of output groups. Each group is a list of output dictionaries.
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

            if abs(output["value_sats"] - other["value_sats"]) <= tolerance_sats:
                group.append(other)
                used.add(j)

        if len(group) >= min_group_size:
            groups.append(group)

    return groups


# -----------------------------
# Score transaction for mixer-like structure
# -----------------------------

def score_mixer_transaction(tx, tolerance_sats=1000, min_group_size=3):
    """
    Score a transaction based on mixer/CoinJoin-like structure.

    This is a lightweight educational heuristic, not proof of mixer use. It
    rewards features commonly associated with mixer-like transactions: many
    inputs, many outputs, multiple unique addresses, and repeated equal-sized
    outputs.

    Args:
        tx: Raw transaction JSON.
        tolerance_sats: Maximum satoshi difference for outputs to count as equal.
        min_group_size: Minimum equal-output group size to flag.

    Returns:
        Dictionary of transaction metrics and a mixer-like score.
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

    equal_groups = detect_equal_output_groups(
        tx,
        tolerance_sats=tolerance_sats,
        min_group_size=min_group_size
    )

    largest_equal_group = 0
    if equal_groups:
        largest_equal_group = max(len(group) for group in equal_groups)

    score = 0
    reasons = []

    # Simple weighted scoring keeps the result explainable for a learning tool.
    if len(inputs) >= 5:
        score += 2
        reasons.append("many inputs")

    if len(outputs) >= 5:
        score += 2
        reasons.append("many outputs")

    if largest_equal_group >= min_group_size:
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
        "Reasons": ", ".join(reasons) if reasons else "no strong mixer-like features"
    }


# -----------------------------
# Analyse downstream mixer-like activity
# -----------------------------

def analyse_address_after_hack(address, max_pages, tolerance_sats, min_group_size):
    """
    Analyse one output address after the hack transaction.

    For one direct output from the hack transaction, this fetches later address
    activity and scores each transaction for mixer-like structure.

    Args:
        address: Bitcoin address to inspect.
        max_pages: Maximum Blockstream pages to fetch.
        tolerance_sats: Equal-output tolerance for mixer scoring.
        min_group_size: Minimum equal-output group size for mixer scoring.

    Returns:
        DataFrame of downstream transactions sorted by mixer-like score.
    """
    txs = get_all_transactions(address, max_pages=max_pages)
    results = [
        score_mixer_transaction(
            tx,
            tolerance_sats=tolerance_sats,
            min_group_size=min_group_size
        )
        for tx in txs
    ]

    df = pd.DataFrame(results)

    if df.empty:
        return df

    return df.sort_values(
        by=["Mixer Score", "Largest Equal Output Group"],
        ascending=False
    ).reset_index(drop=True)


# -----------------------------
# Follow one large hack output
# -----------------------------

def follow_hack_output_multi(address, max_hops=2, top_n=2, min_btc=0.01):
    """
    Follow one hack output with limited branching.

    This does not try to fully reconstruct every path. It follows the largest
    onward outputs for a small number of hops to show whether the stolen funds
    continue in a narrow path or spread into broader distribution.

    Args:
        address: Starting address to follow.
        max_hops: How many hops deep to trace.
        top_n: Number of largest outputs to follow from each address.
        min_btc: Minimum output value to treat as meaningful.

    Returns:
        DataFrame of followed branches.
    """
    rows = []
    current_addresses = [address]

    for hop in range(1, max_hops + 1):
        next_addresses = []

        for addr in current_addresses:
            txs = get_all_transactions(addr, max_pages=2)
            df_outputs = build_transaction_outputs(txs)
            summary = summarise_outputs(df_outputs)

            if summary.empty:
                continue

            filtered = summary[
                (summary["BTC"] >= min_btc) &
                (summary["Output Address"] != addr)
            ].reset_index(drop=True)

            if filtered.empty:
                rows.append({
                    "Hop": hop,
                    "From Address": addr,
                    "To Address": None,
                    "BTC": None,
                    "Interpretation": "No meaningful onward outputs"
                })
                continue

            if len(filtered) > 5:
                interpretation = "Heavy distribution stage"
            elif len(filtered) <= 3:
                interpretation = "Limited branching"
            else:
                interpretation = "Moderate distribution"

            top_outputs = filtered.head(top_n)

            for _, row in top_outputs.iterrows():
                next_addresses.append(row["Output Address"])
                rows.append({
                    "Hop": hop,
                    "From Address": addr,
                    "To Address": row["Output Address"],
                    "BTC": row["BTC"],
                    "Interpretation": interpretation
                })

        current_addresses = next_addresses

        if not current_addresses:
            break

    return pd.DataFrame(rows)


# -----------------------------
# Plot largest hack transaction outputs
# -----------------------------

def plot_hack_outputs(outputs_df, top_n):
    """
    Plot the largest direct outputs from the hack transaction.

    Args:
        outputs_df: DataFrame returned by extract_transaction_outputs().
        top_n: Number of outputs to include.

    Returns:
        Matplotlib figure.
    """
    top_outputs = outputs_df.head(top_n).copy()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(
        top_outputs["Output Address"].astype(str).str[:12],
        top_outputs["Output BTC"]
    )

    ax.set_title("Largest Direct Outputs from Known Hack Transaction")
    ax.set_xlabel("Output address, shortened")
    ax.set_ylabel("BTC")
    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()
    return fig


# -----------------------------
# Streamlit app
# -----------------------------

def main():
    """Render the Streamlit dashboard."""
    st.set_page_config(
        page_title="Binance Hack Flow Explorer",
        page_icon="₿",
        layout="wide"
    )

    st.title("₿ Binance Hack Flow Explorer")
    st.caption(
        "Educational Bitcoin tracing dashboard for inspecting direct hack outputs, "
        "limited downstream branching, and mixer-like transaction patterns."
    )

    st.warning(
        "This tool uses lightweight heuristics for learning purposes. "
        "Mixer-like scoring and downstream flow following are not proof of ownership, "
        "criminal control, or laundering by themselves."
    )

    with st.sidebar:
        st.header("Case settings")
        case_name = st.text_input("Case name", DEFAULT_CASE_NAME)
        hack_txid = st.text_input("Known hack transaction ID", DEFAULT_HACK_TXID)
        min_output_btc = st.number_input("Minimum meaningful output (BTC)", 0.0, 100.0, 0.01, step=0.01)
        max_pages_per_address = st.slider("Max pages per address", 1, 10, 3)
        top_direct_outputs = st.slider("Direct outputs to show", 5, 25, 10)
        downstream_addresses = st.slider("Direct outputs to check downstream", 1, 10, 5)

        st.divider()
        st.header("Mixer-like scoring")
        tolerance_sats = st.number_input("Equal-output tolerance (sats)", 0, 100000, 1000, step=100)
        min_group_size = st.slider("Minimum equal-output group size", 2, 10, 3)

        st.divider()
        st.header("Branch tracing")
        branch_start = st.text_input("Branch start address", "")
        max_hops = st.slider("Max branch hops", 1, 4, 2)
        top_n = st.slider("Top outputs to follow per hop", 1, 5, 2)
        recombined_address = st.text_input("Optional recombined address", DEFAULT_RECOMBINED_ADDRESS)

        run_button = st.button("Run analysis", type="primary")

    if not run_button:
        st.info("Set the controls in the sidebar, then click **Run analysis**.")
        return

    with st.spinner("Fetching known hack transaction..."):
        hack_tx = get_transaction(hack_txid)
        outputs_df = extract_transaction_outputs(hack_tx)

    total_btc = outputs_df["Output BTC"].sum()
    num_outputs = len(outputs_df)
    avg_output = outputs_df["Output BTC"].mean()
    largest_output = outputs_df["Output BTC"].max()

    st.subheader(case_name)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total BTC distributed", f"{total_btc:,.4f}")
    col2.metric("Number of outputs", f"{num_outputs:,}")
    col3.metric("Average output", f"{avg_output:,.4f} BTC")
    col4.metric("Largest output", f"{largest_output:,.4f} BTC")

    overview_tab, direct_tab, mixer_tab, branch_tab, method_tab = st.tabs(
        ["Overview", "Direct outputs", "Mixer-like activity", "Branch trace", "Method notes"]
    )

    with overview_tab:
        st.markdown(
            """
            This case study starts from a known hack transaction and asks:

            1. Where did the BTC go directly after the hack transaction?
            2. Which outputs are large enough to inspect further?
            3. Do later transactions show mixer-like structure?
            4. Does a selected address continue linearly or branch out?
            """
        )

        fig = plot_hack_outputs(outputs_df, top_direct_outputs)
        st.pyplot(fig)

    with direct_tab:
        st.subheader("Direct outputs from known hack transaction")
        st.dataframe(outputs_df, use_container_width=True)

        large_outputs = outputs_df[
            outputs_df["Output BTC"] >= min_output_btc
        ].reset_index(drop=True)

        st.subheader(f"Outputs over {min_output_btc} BTC")
        st.dataframe(large_outputs, use_container_width=True)

    with mixer_tab:
        st.subheader("Downstream mixer-like activity check")

        large_outputs = outputs_df[
            outputs_df["Output BTC"] >= min_output_btc
        ].reset_index(drop=True)

        downstream_results = []
        downstream_detail = {}

        progress = st.progress(0)
        addresses_to_check = large_outputs.head(downstream_addresses)

        for idx, row in addresses_to_check.iterrows():
            address = row["Output Address"]

            if pd.isna(address):
                continue

            df = analyse_address_after_hack(
                address=address,
                max_pages=max_pages_per_address,
                tolerance_sats=tolerance_sats,
                min_group_size=min_group_size
            )

            downstream_detail[address] = df

            if not df.empty:
                best = df.iloc[0]
                downstream_results.append({
                    "Hack Output Address": address,
                    "Hack Output BTC": row["Output BTC"],
                    "Best Downstream TX": best["Transaction ID"],
                    "Best Mixer Score": best["Mixer Score"],
                    "Largest Equal Output Group": best["Largest Equal Output Group"],
                    "Reasons": best["Reasons"]
                })

            progress.progress((idx + 1) / max(len(addresses_to_check), 1))

        downstream_df = pd.DataFrame(downstream_results)

        if downstream_df.empty:
            st.info("No downstream mixer-like activity found in the limited search.")
        else:
            st.dataframe(downstream_df, use_container_width=True)

        with st.expander("Show detailed downstream transaction scores"):
            for address, df in downstream_detail.items():
                st.markdown(f"**{address}**")
                if df.empty:
                    st.write("No transactions returned.")
                else:
                    st.dataframe(df, use_container_width=True)

    with branch_tab:
        st.subheader("Limited branch tracing")

        if not branch_start:
            branch_start = outputs_df.iloc[0]["Output Address"]
            st.caption("No branch start was entered, so the largest direct output was used.")

        branch_df = follow_hack_output_multi(
            address=branch_start,
            max_hops=max_hops,
            top_n=top_n,
            min_btc=min_output_btc
        )

        st.markdown("**Selected branch start address**")
        st.code(branch_start)

        if branch_df.empty:
            st.info("No branch results found for this address.")
        else:
            st.dataframe(branch_df, use_container_width=True)

        with st.expander("Follow optional recombined 1000+ BTC address"):
            if recombined_address:
                recombined_df = follow_hack_output_multi(
                    address=recombined_address,
                    max_hops=1,
                    top_n=top_n,
                    min_btc=min_output_btc
                )

                st.code(recombined_address)

                if recombined_df.empty:
                    st.info("No onward outputs found for the recombined address.")
                else:
                    st.dataframe(recombined_df, use_container_width=True)

    with method_tab:
        st.subheader("What this dashboard is doing")
        st.markdown(
            """
            - Fetches one known transaction by transaction ID.
            - Extracts its direct outputs and ranks them by BTC value.
            - Filters out very small outputs so the analysis focuses on meaningful value flows.
            - Checks downstream transactions from selected output addresses.
            - Scores downstream transactions for mixer-like features such as many inputs, many outputs and repeated equal-sized outputs.
            - Performs a limited branch trace from a selected address.
            """
        )

        st.subheader("Important limitations")
        st.markdown(
            """
            - The mixer score is a heuristic signal, not proof.
            - Exchange batching and service wallets can look mixer-like.
            - Address-level tracing cannot prove human identity.
            - Limited branch tracing may miss later movement if the address has many transactions.
            - Off-chain attribution evidence is still needed for strong investigative claims.
            """
        )


if __name__ == "__main__":
    main()
