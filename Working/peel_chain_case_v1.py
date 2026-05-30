"""Investigator-style Streamlit dashboard for a peel-chain case study.

This app turns the peel-chain tracing script into a case-study dashboard. It
starts from a seed Bitcoin address, follows the largest onward outputs as a
possible peel-chain path, estimates peeled-off amounts and displays the main
flow, branch analysis and raw evidence tables.

Important: this is an educational heuristic tool. The inferred flow and labels
are signals for discussion, not proof of ownership, attribution or criminal
activity.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# DEFAULT CONFIG
# -----------------------------

DEFAULT_CASE_NAME = "Dharma / Xorist"
DEFAULT_SEED_ADDRESS = "1NJNG57hFPPcmSmFYbxKmL33uc5nLwYLCK"

DEFAULT_BRANCH_TOP_N = 3
DEFAULT_BRANCH_MAX_HOPS = 3
DEFAULT_BRANCH_MAX_PAGES_PER_ADDRESS = 2
DEFAULT_MAX_HOPS = 15
DEFAULT_GRAPH_STEPS = 6
DEFAULT_MIN_BTC = 0.001
SATOSHIS_PER_BTC = 100_000_000


# -----------------------------
# 1. Get all confirmed transactions for an address
# -----------------------------
@st.cache_data(show_spinner=False)
def get_all_transactions(address: str, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch confirmed transactions for a Bitcoin address from Blockstream.

    Args:
        address: Bitcoin address to query.
        max_pages: Optional limit on pagination pages. This prevents branch
            tracing from spending too long on high-activity addresses.

    Returns:
        A list of confirmed transaction dictionaries returned by Blockstream.
    """
    all_txs = []
    last_seen = None
    page_count = 0

    while True:
        # Blockstream returns 25 transactions per page. After the first page,
        # the last transaction ID is used as the pagination cursor.
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
                # Retry short API failures because public blockchain APIs can
                # occasionally timeout or rate-limit requests.
                time.sleep(2)
        else:
            # If all retries fail, return whatever was fetched so far rather
            # than crashing the app during a live demonstration.
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
# 2. Build transaction_inputs table
# -----------------------------
def build_transaction_inputs(all_txs: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create a readable input table from raw transaction JSON.

    Args:
        all_txs: Raw transaction dictionaries from Blockstream.

    Returns:
        DataFrame with one row per input.
    """
    input_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vin in enumerate(tx["vin"]):
            prevout = vin.get("prevout", {})

            input_rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Input Index": i,
                "Input Address": prevout.get("scriptpubkey_address"),
                "Input Value": prevout.get("value"),
            })

    df_inputs = pd.DataFrame(input_rows)

    if not df_inputs.empty:
        df_inputs["Timestamp"] = pd.to_datetime(
            df_inputs["Timestamp"], unit="s", errors="coerce"
        )
        df_inputs["BTC"] = df_inputs["Input Value"] / SATOSHIS_PER_BTC

    return df_inputs


# -----------------------------
# 3. Build transaction_outputs table
# -----------------------------
def build_transaction_outputs(all_txs: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create a readable output table from raw transaction JSON.

    Args:
        all_txs: Raw transaction dictionaries from Blockstream.

    Returns:
        DataFrame with one row per output.
    """
    output_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vout in enumerate(tx["vout"]):
            output_rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Output Index": i,
                "Output Address": vout.get("scriptpubkey_address"),
                "Output Value": vout.get("value"),
            })

    df_outputs = pd.DataFrame(output_rows)

    if not df_outputs.empty:
        df_outputs["Timestamp"] = pd.to_datetime(
            df_outputs["Timestamp"], unit="s", errors="coerce"
        )
        df_outputs["BTC"] = df_outputs["Output Value"] / SATOSHIS_PER_BTC

    return df_outputs


# -----------------------------
# 4. Summarise outputs by address
# -----------------------------
def summarise_outputs(df_outputs: pd.DataFrame) -> pd.DataFrame:
    """Summarise total BTC sent to each output address.

    Args:
        df_outputs: Output-level transaction table.

    Returns:
        DataFrame ranked by total BTC received.
    """
    if df_outputs.empty:
        return pd.DataFrame(columns=["Output Address", "Output Value", "BTC"])

    summary = (
        df_outputs
        .groupby("Output Address", dropna=False)["Output Value"]
        .sum()
        .reset_index()
        .sort_values("Output Value", ascending=False)
        .reset_index(drop=True)
    )

    summary["BTC"] = (summary["Output Value"] / SATOSHIS_PER_BTC).round(8)
    return summary


# -----------------------------
# 5. Find outputs above threshold
# -----------------------------
def find_large_outputs(df_outputs: pd.DataFrame, min_btc: float = DEFAULT_MIN_BTC) -> pd.DataFrame:
    """Filter outputs above a minimum BTC threshold.

    Args:
        df_outputs: Output-level transaction table.
        min_btc: Minimum BTC value to keep.

    Returns:
        DataFrame of outputs sorted largest to smallest.
    """
    if df_outputs.empty:
        return pd.DataFrame()

    df_outputs = df_outputs.copy()
    df_outputs["BTC"] = df_outputs["Output Value"] / SATOSHIS_PER_BTC

    return df_outputs[df_outputs["BTC"] >= min_btc].sort_values(
        by="BTC",
        ascending=False,
    )


# -----------------------------
# 6. Follow peel-chain path
# -----------------------------
def follow_largest_outputs(
    start_address: str,
    max_hops: int = DEFAULT_MAX_HOPS,
    min_btc: float = DEFAULT_MIN_BTC,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Follow the largest onward output as a possible peel-chain path.

    Args:
        start_address: Address where the main flow begins.
        max_hops: Maximum number of hops to follow.
        min_btc: Minimum BTC threshold for meaningful outputs.

    Returns:
        A tuple containing hop result dictionaries and human-readable log lines.
    """
    current_address = start_address
    hop_results = []
    seen_addresses = set()
    logs = []

    for hop in range(1, max_hops + 1):
        logs.append(f"Hop {hop}: analysing {current_address}")

        if current_address in seen_addresses:
            logs.append("Address already seen. Peel chain likely looped. Stopping trace.")
            break

        seen_addresses.add(current_address)
        txs = get_all_transactions(current_address)

        df_inputs_hop = build_transaction_inputs(txs)
        df_outputs_hop = build_transaction_outputs(txs)

        summary = summarise_outputs(df_outputs_hop)
        filtered = summary[summary["BTC"] >= min_btc].reset_index(drop=True)

        if filtered.empty:
            logs.append("No outputs above threshold. Stopping trace.")
            break

        # Do not follow an output back to the same address. The goal is to
        # identify the next address in the forward money flow.
        candidates = filtered[
            filtered["Output Address"] != current_address
        ].reset_index(drop=True)

        if candidates.empty:
            logs.append("No forward address found. Stopping trace.")
            break

        # Peel-chain simplification: treat the largest onward output as the
        # likely continuing change flow. Smaller differences are later treated
        # as estimated peeled-off amounts.
        top_output = candidates.iloc[0]
        next_address = top_output["Output Address"]
        current_btc = top_output["BTC"]

        if hop_results:
            previous_btc = hop_results[-1]["btc"]

            if current_btc > previous_btc:
                logs.append("Flow increased. Likely no longer a clean peel chain. Stopping trace.")
                break

            if (previous_btc - current_btc) > previous_btc * 0.2:
                logs.append("Large drop detected. Likely exit to service. Stopping trace.")
                break

            if current_btc < 0.01:
                logs.append("Value too small. Likely dust/noise. Stopping trace.")
                break

        hop_results.append({
            "hop": hop,
            "address": current_address,
            "next_address": next_address,
            "btc": current_btc,
            "summary": filtered,
            "inputs": df_inputs_hop,
            "outputs": df_outputs_hop,
        })

        current_address = next_address

    logs.append(f"Trace complete. Total hops analysed: {len(hop_results)}")
    return hop_results, logs


# -----------------------------
# 7. Follow limited branches
# -----------------------------
def trace_top_branches(
    start_address: str,
    max_hops: int = DEFAULT_BRANCH_MAX_HOPS,
    top_n: int = DEFAULT_BRANCH_TOP_N,
    min_btc: float = DEFAULT_MIN_BTC,
    max_pages_per_address: int = DEFAULT_BRANCH_MAX_PAGES_PER_ADDRESS,
) -> pd.DataFrame:
    """Trace a small number of top branches from the main flow.

    Args:
        start_address: Address to begin branch tracing from.
        max_hops: Maximum branch depth.
        top_n: Number of top outputs to follow per address.
        min_btc: Minimum BTC threshold for meaningful outputs.
        max_pages_per_address: API page limit per branch address.

    Returns:
        DataFrame describing limited branch flows.
    """
    results = []
    queue = [(start_address, 0)]
    seen = set()

    while queue:
        current_address, depth = queue.pop(0)

        if depth >= max_hops:
            continue

        if current_address in seen:
            continue

        seen.add(current_address)

        # Branch tracing is capped so high-activity addresses do not run forever.
        txs = get_all_transactions(current_address, max_pages=max_pages_per_address)
        is_high_activity = len(txs) >= 50

        df_outputs_branch = build_transaction_outputs(txs)
        summary = summarise_outputs(df_outputs_branch)

        filtered = summary[
            (summary["BTC"] >= min_btc) &
            (summary["Output Address"] != current_address)
        ].reset_index(drop=True)

        top_outputs = filtered.head(top_n)

        for i, row in top_outputs.iterrows():
            btc_value = row["BTC"]

            # Labels are intentionally simple for an educational app. They are
            # descriptive hints, not verified attribution labels.
            if is_high_activity or btc_value > 1000:
                label = "Service / Exchange"
            elif i == 0:
                label = "Main flow"
            elif btc_value > 1:
                label = "Branch"
            else:
                label = "Peel"

            results.append({
                "Depth": depth + 1,
                "From Address": current_address,
                "To Address": row["Output Address"],
                "BTC": btc_value,
                "Type": label,
                "High Activity": is_high_activity,
            })

            queue.append((row["Output Address"], depth + 1))

    return pd.DataFrame(results)


# -----------------------------
# 8. Build peel-chain steps
# -----------------------------
def build_peel_steps(
    seed_address: str,
    seed_btc: float,
    main_flow_address: str,
    main_flow_btc: float,
    hop_results: List[Dict[str, Any]],
) -> pd.DataFrame:
    """Create a clean step table for the main peel-chain path.

    Args:
        seed_address: Original seed or collection address.
        seed_btc: Total BTC associated with the seed address in this analysis.
        main_flow_address: First address in the inferred main flow.
        main_flow_btc: BTC value sent to the main flow address.
        hop_results: Results returned by follow_largest_outputs().

    Returns:
        DataFrame containing ordered peel-chain steps.
    """
    steps = [
        {
            "Step": 0,
            "Address": seed_address,
            "Role": "Seed / collection address",
            "BTC": seed_btc,
        },
        {
            "Step": 1,
            "Address": main_flow_address,
            "Role": "Main forward flow",
            "BTC": main_flow_btc,
        },
    ]

    for result in hop_results:
        steps.append({
            "Step": result["hop"] + 1,
            "Address": result["next_address"],
            "Role": "Next largest output",
            "BTC": result["btc"],
        })

    return pd.DataFrame(steps)


# -----------------------------
# 9. Detect peeled amounts
# -----------------------------
def add_peeled_amounts(peel_df: pd.DataFrame) -> pd.DataFrame:
    """Estimate peeled BTC by comparing each step with the next step.

    Args:
        peel_df: Ordered peel-chain step table.

    Returns:
        Copy of peel_df with estimated peeled amounts added.
    """
    peel_df = peel_df.copy()

    peel_df["Next BTC"] = peel_df["BTC"].shift(-1)
    peel_df["Estimated Peeled BTC"] = peel_df["BTC"] - peel_df["Next BTC"]
    peel_df["Estimated Peeled BTC"] = peel_df["Estimated Peeled BTC"].round(6)

    # Step 0 is the collection/entry point, so peeled amount starts from the
    # main flow after the initial collection transfer.
    peel_df.loc[peel_df["Next BTC"].isna(), "Estimated Peeled BTC"] = None
    peel_df.loc[peel_df["Step"] == 0, "Estimated Peeled BTC"] = None

    return peel_df


# -----------------------------
# 10. Draw simplified peel-chain graph
# -----------------------------
def create_peel_chain_graph(peel_df: pd.DataFrame, case_name: str) -> plt.Figure:
    """Create a simplified peel-chain NetworkX graph.

    Args:
        peel_df: Peel-chain step table with estimated peeled amounts.
        case_name: Display name for the case study.

    Returns:
        Matplotlib figure for Streamlit rendering.
    """
    G = nx.DiGraph()
    labels = {}
    edge_labels = {}
    pos = {}
    node_colors = []

    for i, row in peel_df.iterrows():
        main_node = f"Step {row['Step']}"
        pos[main_node] = (i * 4, 1)

        if row["Step"] == 0:
            role_text = "Entry"
            node_color = "#f8c471"
        elif row["Step"] == 1:
            role_text = "Chain starts"
            node_color = "#85c1e9"
        else:
            role_text = "Main flow"
            node_color = "#aed6f1"

        labels[main_node] = (
            f"Step {row['Step']}\n"
            f"{role_text}\n"
            f"{round(row['BTC'], 4)} BTC"
        )

        G.add_node(main_node)
        node_colors.append(node_color)

    for i in range(len(peel_df) - 1):
        G.add_edge(f"Step {i}", f"Step {i + 1}")

    for i, row in peel_df.iterrows():
        peeled_value = row.get("Estimated Peeled BTC")

        if pd.notna(peeled_value) and peeled_value > 0:
            peel_node = f"Peel {row['Step']}"
            source = f"Step {row['Step']}"

            pos[peel_node] = (i * 4, 0)
            labels[peel_node] = f"Peeled\n{round(peeled_value, 4)} BTC"

            G.add_node(peel_node)
            G.add_edge(source, peel_node)
            node_colors.append("#f5b7b1")

            edge_labels[(source, peel_node)] = f"{round(peeled_value, 4)} BTC"

    fig, ax = plt.subplots(figsize=(22, 6))

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_size=3300,
        node_color=node_colors,
        edge_color="#566573",
        linewidths=1.2,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=18,
    )

    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7, ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, ax=ax)

    ax.set_title(f"{case_name} Peel-Chain Flow", pad=20, fontsize=16)
    ax.axis("off")
    fig.tight_layout()
    return fig


# -----------------------------
# 11. Create peel statistics
# -----------------------------
def calculate_peel_statistics(peel_df: pd.DataFrame, max_hops: int) -> pd.DataFrame:
    """Calculate summary statistics for detected peel events.

    Args:
        peel_df: Peel-chain step table with estimated peeled amounts.
        max_hops: Configured maximum hop count.

    Returns:
        Two-column DataFrame of statistic names and values.
    """
    valid_peels = peel_df["Estimated Peeled BTC"].dropna()
    valid_peels = valid_peels[valid_peels > 0]

    if valid_peels.empty:
        return pd.DataFrame({
            "Metric": ["Peel events detected"],
            "Value": ["0"],
        })

    percentage = None
    if len(peel_df) > 1 and peel_df.iloc[1]["BTC"]:
        percentage = (valid_peels.sum() / peel_df.iloc[1]["BTC"]) * 100

    metrics = [
        ("Number of peel events", len(valid_peels)),
        ("Total BTC peeled", round(valid_peels.sum(), 4)),
        ("Average peel size", round(valid_peels.mean(), 4)),
        ("Largest peel", round(valid_peels.max(), 4)),
        ("Smallest peel", round(valid_peels.min(), 4)),
        ("Maximum depth analysed", f"{max_hops} hops"),
    ]

    if percentage is not None:
        metrics.append(("Percentage of total flow peeled", f"{round(percentage, 2)}%"))

    return pd.DataFrame(metrics, columns=["Metric", "Value"])


# -----------------------------
# 12. Select one peel event for deeper analysis
# -----------------------------
def select_largest_peel_event(peel_df: pd.DataFrame) -> Optional[pd.Series]:
    """Select the step with the largest estimated peeled amount.

    Args:
        peel_df: Peel-chain step table with estimated peeled amounts.

    Returns:
        Row for the largest peel event, or None if none exists.
    """
    valid_peels = peel_df.dropna(subset=["Estimated Peeled BTC"])
    valid_peels = valid_peels[valid_peels["Estimated Peeled BTC"] > 0]

    if valid_peels.empty:
        return None

    return valid_peels.loc[valid_peels["Estimated Peeled BTC"].idxmax()]


# -----------------------------
# 13. Inspect selected peel address
# -----------------------------
def inspect_selected_peel_address(address: str, min_btc: float = DEFAULT_MIN_BTC) -> pd.DataFrame:
    """Inspect onward outputs from a selected peel-chain address.

    Args:
        address: Address selected for closer inspection.
        min_btc: Minimum BTC threshold for meaningful outputs.

    Returns:
        DataFrame of top onward outputs.
    """
    txs = get_all_transactions(address, max_pages=3)
    df_outputs = build_transaction_outputs(txs)
    summary = summarise_outputs(df_outputs)

    filtered = summary[
        (summary["BTC"] >= min_btc) &
        (summary["Output Address"] != address)
    ].reset_index(drop=True)

    return filtered


# -----------------------------
# 14. Run full analysis
# -----------------------------
def run_analysis(
    case_name: str,
    seed_address: str,
    min_btc: float,
    max_hops: int,
    graph_steps: int,
    branch_max_hops: int,
    branch_top_n: int,
    branch_max_pages_per_address: int,
) -> Dict[str, Any]:
    """Run the full peel-chain workflow and collect app outputs.

    Args:
        case_name: Display name for the case study.
        seed_address: Seed Bitcoin address.
        min_btc: Minimum BTC threshold.
        max_hops: Maximum hops for main trace.
        graph_steps: Number of steps shown in simplified graph.
        branch_max_hops: Maximum hops for branch trace.
        branch_top_n: Number of branches followed per address.
        branch_max_pages_per_address: API page limit for branch tracing.

    Returns:
        Dictionary containing tables, logs, graph and summary values.
    """
    all_txs = get_all_transactions(seed_address)
    df_inputs = build_transaction_inputs(all_txs)
    df_outputs = build_transaction_outputs(all_txs)
    outputs_summary = summarise_outputs(df_outputs)
    large_outputs = find_large_outputs(df_outputs, min_btc=min_btc)

    if outputs_summary.empty:
        raise ValueError("No output data found for this seed address.")

    seed_match = outputs_summary.loc[
        outputs_summary["Output Address"] == seed_address,
        "BTC",
    ]

    seed_btc = float(seed_match.iloc[0]) if not seed_match.empty else 0.0

    main_candidates = outputs_summary[
        outputs_summary["Output Address"] != seed_address
    ].reset_index(drop=True)

    if main_candidates.empty:
        raise ValueError("Could not identify a main forward address from the seed address.")

    main_flow_row = main_candidates.iloc[0]
    main_flow_address = main_flow_row["Output Address"]
    main_flow_btc = float(main_flow_row["BTC"])

    hop_results, trace_logs = follow_largest_outputs(
        start_address=main_flow_address,
        max_hops=max_hops,
        min_btc=min_btc,
    )

    peel_df = build_peel_steps(
        seed_address=seed_address,
        seed_btc=seed_btc,
        main_flow_address=main_flow_address,
        main_flow_btc=main_flow_btc,
        hop_results=hop_results,
    )
    peel_df = add_peeled_amounts(peel_df)

    stats_df = calculate_peel_statistics(peel_df, max_hops=max_hops)
    graph_fig = create_peel_chain_graph(peel_df.head(graph_steps), case_name=case_name)

    selected_peel = select_largest_peel_event(peel_df)
    selected_outputs = pd.DataFrame()
    if selected_peel is not None:
        selected_outputs = inspect_selected_peel_address(
            address=selected_peel["Address"],
            min_btc=min_btc,
        )

    branch_df = trace_top_branches(
        start_address=main_flow_address,
        max_hops=branch_max_hops,
        top_n=branch_top_n,
        min_btc=min_btc,
        max_pages_per_address=branch_max_pages_per_address,
    )

    return {
        "case_name": case_name,
        "seed_address": seed_address,
        "all_txs": all_txs,
        "df_inputs": df_inputs,
        "df_outputs": df_outputs,
        "outputs_summary": outputs_summary,
        "large_outputs": large_outputs,
        "seed_btc": seed_btc,
        "main_flow_address": main_flow_address,
        "main_flow_btc": main_flow_btc,
        "hop_results": hop_results,
        "trace_logs": trace_logs,
        "peel_df": peel_df,
        "stats_df": stats_df,
        "graph_fig": graph_fig,
        "selected_peel": selected_peel,
        "selected_outputs": selected_outputs,
        "branch_df": branch_df,
    }



# -----------------------------
# STREAMLIT APP
# -----------------------------
def render_metric_row(results: Dict[str, Any]) -> None:
    """Render headline case metrics."""
    valid_peels = results["peel_df"]["Estimated Peeled BTC"].dropna()
    valid_peels = valid_peels[valid_peels > 0]

    total_peeled = valid_peels.sum() if not valid_peels.empty else 0
    largest_peel = valid_peels.max() if not valid_peels.empty else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Seed total", f"{results['seed_btc']:.4f} BTC")
    col2.metric("First main flow", f"{results['main_flow_btc']:.4f} BTC")
    col3.metric("Peel events", len(valid_peels))
    col4.metric("Largest peel", f"{largest_peel:.4f} BTC")
    col5.metric("Hops analysed", len(results["hop_results"]))

    col6, col7, col8 = st.columns(3)
    col6.metric("Total peeled", f"{total_peeled:.4f} BTC")
    col7.metric("Transactions fetched", len(results["all_txs"]))
    col8.metric("Branch rows", len(results["branch_df"]))


def main() -> None:
    """Render the Streamlit app."""
    st.set_page_config(
        page_title="Peel-Chain Tracing Case Study",
        page_icon="₿",
        layout="wide",
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
        .btc-coin {
            width: 76px;
            height: 76px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 42px;
            font-weight: 800;
            color: white;
            background: radial-gradient(circle at 30% 30%, #ffd166, #f7931a 65%, #b45309);
            box-shadow: 0 8px 25px rgba(0,0,0,0.18);
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
    st.title("Peel-Chain Tracing Case Study")
    st.caption("A case study showing how a high-value Bitcoin flow can be followed through repeated onward movements.")

    st.markdown(
        f"""
        <div class="case-card">
            <h3>Case focus</h3>
            <p>
                This case starts from a ransomware-associated Bitcoin address and follows the dominant onward flow
                visible in its related transaction history.
            </p>
            <p>
                The aim is to show a peel-chain style tracing method: a large value continues forward while smaller
                values are separated along the way.
            </p>
            <p class="small-note">
                Seed address: <code>{DEFAULT_SEED_ADDRESS}</code>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    st.header("How the analysis works")
    st.markdown(
        """
        <div class="case-card">
            <h3>Peel-chain tracing</h3>
            <p>
                A peel chain is a pattern where Bitcoin moves through a series of transactions. At each step,
                most of the value continues forward and a smaller amount is split away.
            </p>
            <p>
                This prototype uses a simple heuristic: it follows the largest onward output as the main flow,
                then estimates the peeled amount by comparing one step with the next.
            </p>
            <p class="small-note">
                The labels are tracing indicators. They do not prove ownership, attribution or criminal activity.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.spinner("Loading peel-chain transaction data from Blockstream..."):
        try:
            results = run_analysis(
                case_name=DEFAULT_CASE_NAME,
                seed_address=DEFAULT_SEED_ADDRESS,
                min_btc=DEFAULT_MIN_BTC,
                max_hops=DEFAULT_MAX_HOPS,
                graph_steps=DEFAULT_GRAPH_STEPS,
                branch_max_hops=DEFAULT_BRANCH_MAX_HOPS,
                branch_top_n=DEFAULT_BRANCH_TOP_N,
                branch_max_pages_per_address=DEFAULT_BRANCH_MAX_PAGES_PER_ADDRESS,
            )
        except Exception as exc:
            st.error(f"Could not complete the peel-chain trace: {exc}")
            st.stop()

    render_metric_row(results)

    first_main_btc = results["main_flow_btc"]
    latest_btc = results["peel_df"].iloc[min(len(results["peel_df"]) - 1, DEFAULT_GRAPH_STEPS - 1)]["BTC"]
    valid_peels = results["peel_df"]["Estimated Peeled BTC"].dropna()
    valid_peels = valid_peels[valid_peels > 0]
    total_peeled = valid_peels.sum() if not valid_peels.empty else 0

    st.markdown(
        f"""
        <div class="case-card">
            <h3>What the trace shows</h3>
            <p>
                The main flow begins at approximately <b>{first_main_btc:.4f} BTC</b> and continues across
                successive hops. Across the displayed path, the app estimates <b>{total_peeled:.4f} BTC</b>
                separated from the continuing flow.
            </p>
            <p>
                This makes the case useful as a peel-chain example: the interesting feature is not a single
                transaction, but the repeated forward movement of value.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("1. Peel-chain flow")
    st.write(
        "This graph is the main visual story: the dominant value moves forward step by step, while peeled amounts split away from the path."
    )
    st.pyplot(results["graph_fig"], use_container_width=True)

    st.subheader("2. Step-by-step trace")
    st.write("The table shows the address followed at each step and the estimated BTC separated before the next step.")
    st.dataframe(
        results["peel_df"][["Step", "Address", "Role", "BTC", "Estimated Peeled BTC"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("3. Top outputs linked to the seed transaction history")
    st.write(
        "This table explains why the high-value path was selected: the trace follows the largest onward output visible from the seed address transaction history."
    )
    st.dataframe(
        results["outputs_summary"][["Output Address", "BTC"]].head(10),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("4. Peel-chain indicators")
    st.dataframe(results["stats_df"], use_container_width=True, hide_index=True)

    with st.expander("Show branch analysis"):
        branch_df = results["branch_df"]
        if branch_df.empty:
            st.write("No branch results found above the selected threshold.")
        else:
            branch_df = branch_df.copy()
            branch_df["Type"] = branch_df["Type"].replace({"Service / Exchange": "High-activity destination"})
            st.dataframe(branch_df, use_container_width=True, hide_index=True)

    with st.expander("Show raw evidence tables"):
        st.markdown("**Large individual outputs**")
        large_outputs = results["large_outputs"]
        if large_outputs.empty:
            st.write("No large outputs found above the selected threshold.")
        else:
            st.dataframe(
                large_outputs[["Transaction ID", "Timestamp", "Output Address", "BTC"]].head(100),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**Input table**")
        st.dataframe(results["df_inputs"].head(200), use_container_width=True, hide_index=True)

        st.markdown("**Output table**")
        st.dataframe(results["df_outputs"].head(200), use_container_width=True, hide_index=True)

    st.subheader("Transaction summary")
    summary_rows = [
        {
            "Step": "1. Starting point",
            "What happened": "The trace begins from the ransomware-associated seed address.",
            "BTC": f"Seed total in related history: {results['seed_btc']:.8f} BTC",
        },
        {
            "Step": "2. Main lead selected",
            "What happened": "The app identifies the largest onward output visible from the seed address transaction history.",
            "BTC": f"{first_main_btc:.8f} BTC",
        },
        {
            "Step": "3. Peel-chain path",
            "What happened": "The largest onward output is followed across successive hops.",
            "BTC": f"{latest_btc:.8f} BTC remains at the last displayed step",
        },
        {
            "Step": "4. Peeled amounts",
            "What happened": "The difference between one main-flow step and the next is treated as an estimated peeled amount.",
            "BTC": f"{total_peeled:.8f} BTC estimated across displayed path",
        },
    ]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.markdown(
        """
        <div class="case-card">
            <h3>Important limitation</h3>
            <p>
                This is a tracing heuristic. It shows a peel-chain style structure, but it does not prove that
                every address belongs to the same owner. Exchange batching, wallet behaviour, CoinJoin and other
                privacy techniques can weaken simple tracing assumptions.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("References")
    with st.expander("Show references and data sources"):
        st.markdown(
            """
            Blockstream (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/explorer-api (Accessed: 26 May 2026).

            Kappos, G., Yousaf, H., Stütz, R., Rollet, S., Haslhofer, B. and Meiklejohn, S. (2022) 'How to Peel a Million: Validating and Expanding Bitcoin Clusters', *31st USENIX Security Symposium*, pp. 2207–2224.
            """
        )


if __name__ == "__main__":
    main()
