"""Locky campaign-scale map (exploratory Streamlit app).

This app is separate from the clean CIOH case study app.

Goal:
- Start from the local Ransomwhere JSON file.
- Filter Locky-labelled addresses to a manageable sample.
- Query Blockstream for each selected address.
- Build a larger NetworkX map showing:
    Locky-labelled addresses -> transactions -> output addresses.
- Highlight possible consolidation hubs where multiple Locky-labelled inputs
  appear in the same transaction, or where large BTC outputs are created.

Important:
This is exploratory. It does not prove real-world identity.
It shows blockchain patterns that can support investigation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(
    page_title="Locky Campaign Map",
    page_icon="₿",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .case-card {
        border: 1px solid rgba(120, 120, 120, 0.25);
        border-radius: 16px;
        padding: 1rem 1.2rem;
        background: rgba(250, 250, 250, 0.04);
        margin-bottom: 1rem;
    }
    .small-note {font-size: 0.92rem; color: #666;}
    .warn-note {font-size: 0.92rem; color: #9a6700;}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Config
# -----------------------------
SATOSHIS_PER_BTC = 100_000_000
REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.15
DEFAULT_JSON_PATH = "ransomwhere_data.json"


# -----------------------------
# Small helpers
# -----------------------------
def sats_to_btc(value: int | float | None) -> float:
    """Convert satoshis to BTC."""
    if value is None:
        return 0.0
    return float(value) / SATOSHIS_PER_BTC


def is_bitcoin_address(value: Any) -> bool:
    """Simple visual helper only. Not an attribution method."""
    text = str(value)
    return text.startswith(("1", "3", "bc1"))


def load_ransomwhere_json(json_path: str) -> pd.DataFrame:
    """Load Ransomwhere JSON into a dataframe."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Could not find {json_path}. Put it in the same folder as this app, or enter the full path.")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    df = pd.DataFrame(data)

    if "transactions" in df.columns:
        df["tx_count"] = df["transactions"].apply(lambda x: len(x) if isinstance(x, list) else 0)
    else:
        df["tx_count"] = 0

    if "balance" in df.columns:
        df["balance_btc"] = df["balance"].apply(sats_to_btc)
    else:
        df["balance_btc"] = 0.0

    return df


@st.cache_data(show_spinner=False)
def fetch_address_transactions(address: str) -> list[dict[str, Any]]:
    """Fetch confirmed transactions for one Bitcoin address from Blockstream.

    This fetches all pages. For most Locky candidate addresses, tx history is small.
    """
    all_txs: list[dict[str, Any]] = []
    last_seen: str | None = None

    while True:
        if last_seen is None:
            url = f"https://blockstream.info/api/address/{address}/txs"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"

        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        page = response.json()

        if not page:
            break

        all_txs.extend(page)

        if len(page) < 25:
            break

        last_seen = page[-1]["txid"]
        time.sleep(API_SLEEP_SECONDS)

    return all_txs


def extract_tx_rows(txs: list[dict[str, Any]], source_seed: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Turn raw Blockstream transactions into input and output rows."""
    input_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []

    for tx in txs:
        txid = tx.get("txid")

        for vin in tx.get("vin", []):
            prevout = vin.get("prevout") or {}
            input_rows.append(
                {
                    "source_seed": source_seed,
                    "txid": txid,
                    "input_address": prevout.get("scriptpubkey_address", "Unknown"),
                    "input_btc": sats_to_btc(prevout.get("value")),
                }
            )

        for vout in tx.get("vout", []):
            output_rows.append(
                {
                    "source_seed": source_seed,
                    "txid": txid,
                    "output_address": vout.get("scriptpubkey_address", "Unknown"),
                    "output_btc": sats_to_btc(vout.get("value")),
                }
            )

    return pd.DataFrame(input_rows), pd.DataFrame(output_rows)


def build_campaign_data(addresses: list[str], progress_bar=None, status_text=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch transactions for selected addresses and build input/output tables."""
    all_inputs: list[pd.DataFrame] = []
    all_outputs: list[pd.DataFrame] = []

    total = len(addresses)

    for i, address in enumerate(addresses, start=1):
        if status_text is not None:
            status_text.write(f"Fetching {i}/{total}: {address}")
        if progress_bar is not None:
            progress_bar.progress(i / total)

        txs = fetch_address_transactions(address)
        df_in, df_out = extract_tx_rows(txs, source_seed=address)
        all_inputs.append(df_in)
        all_outputs.append(df_out)
        time.sleep(API_SLEEP_SECONDS)

    df_inputs = pd.concat(all_inputs, ignore_index=True).drop_duplicates() if all_inputs else pd.DataFrame()
    df_outputs = pd.concat(all_outputs, ignore_index=True).drop_duplicates() if all_outputs else pd.DataFrame()

    return df_inputs, df_outputs


def summarise_transactions(
    df_inputs: pd.DataFrame,
    df_outputs: pd.DataFrame,
    locky_addresses: set[str],
) -> pd.DataFrame:
    """Create one row per transaction with useful campaign-scale features."""
    if df_inputs.empty or df_outputs.empty:
        return pd.DataFrame()

    in_summary = (
        df_inputs.groupby("txid")
        .agg(
            input_count=("input_address", "nunique"),
            total_input_btc=("input_btc", "sum"),
            locky_input_count=("input_address", lambda s: len(set(s) & locky_addresses)),
        )
        .reset_index()
    )

    out_summary = (
        df_outputs.groupby("txid")
        .agg(
            output_count=("output_address", "nunique"),
            total_output_btc=("output_btc", "sum"),
            largest_output_btc=("output_btc", "max"),
        )
        .reset_index()
    )

    summary = in_summary.merge(out_summary, on="txid", how="outer").fillna(0)
    summary["possible_cioh"] = summary["input_count"] >= 2
    summary["strong_locky_cioh"] = summary["locky_input_count"] >= 2

    return summary.sort_values(
        ["locky_input_count", "total_input_btc"],
        ascending=[False, False],
    )


def build_campaign_graph(
    df_inputs: pd.DataFrame,
    df_outputs: pd.DataFrame,
    locky_addresses: set[str],
    min_locky_inputs: int,
    min_total_input_btc: float,
    max_transactions: int,
    max_outputs_per_tx: int,
) -> nx.DiGraph:
    """Build a campaign graph from selected transactions.

    The graph is deliberately filtered so it stays readable.
    """
    G = nx.DiGraph()

    if df_inputs.empty or df_outputs.empty:
        return G

    tx_summary = summarise_transactions(df_inputs, df_outputs, locky_addresses)

    selected_txids = tx_summary[
        (tx_summary["locky_input_count"] >= min_locky_inputs)
        & (tx_summary["total_input_btc"] >= min_total_input_btc)
    ]["txid"].head(max_transactions).tolist()

    for txid in selected_txids:
        tx_node = f"tx:{txid}"
        G.add_node(tx_node, node_type="transaction", label=txid)

        tx_inputs = df_inputs[df_inputs["txid"] == txid].copy()
        tx_outputs = df_outputs[df_outputs["txid"] == txid].copy()

        # Add all Locky-labelled inputs, plus any non-Locky inputs if there are not too many.
        for _, row in tx_inputs.iterrows():
            addr = row["input_address"]
            value = row["input_btc"]

            node_type = "locky_input" if addr in locky_addresses else "other_input"
            G.add_node(addr, node_type=node_type, label=addr)
            G.add_edge(addr, tx_node, value=value)

        # Show biggest outputs only, otherwise a transaction with many outputs becomes unreadable.
        tx_outputs = tx_outputs.sort_values("output_btc", ascending=False).head(max_outputs_per_tx)

        for _, row in tx_outputs.iterrows():
            addr = row["output_address"]
            value = row["output_btc"]

            node_type = "locky_output" if addr in locky_addresses else "output"
            # Treat big outputs as hubs for visual impact.
            if value >= 50:
                node_type = "large_output"

            G.add_node(addr, node_type=node_type, label=addr)
            G.add_edge(tx_node, addr, value=value)

    return G


def draw_campaign_graph(G: nx.DiGraph, title: str) -> plt.Figure:
    """Draw the campaign graph without node labels.

    Full addresses are shown in tables below, not on the graph, to keep it readable.
    """
    fig, ax = plt.subplots(figsize=(17, 10))

    if G.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No graph to display with current filters", ha="center", va="center", fontsize=14)
        ax.axis("off")
        return fig

    pos = nx.spring_layout(G, seed=42, k=0.65, iterations=120)

    node_types = nx.get_node_attributes(G, "node_type")

    colours = []
    sizes = []
    for node in G.nodes():
        node_type = node_types.get(node, "other")

        if node_type == "locky_input":
            colours.append("#ef4444")  # red
            sizes.append(360)
        elif node_type == "transaction":
            colours.append("#111827")  # black
            sizes.append(170)
        elif node_type == "large_output":
            colours.append("#f59e0b")  # orange
            sizes.append(520)
        elif node_type == "locky_output":
            colours.append("#a855f7")  # purple
            sizes.append(420)
        elif node_type == "output":
            colours.append("#93c5fd")  # blue
            sizes.append(340)
        else:
            colours.append("#d1d5db")  # grey
            sizes.append(260)

    edge_widths = []
    for _, _, data in G.edges(data=True):
        value = float(data.get("value", 0))
        if value >= 100:
            edge_widths.append(2.8)
        elif value >= 50:
            edge_widths.append(2.2)
        elif value >= 10:
            edge_widths.append(1.6)
        else:
            edge_widths.append(0.9)

    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        arrows=True,
        arrowsize=12,
        width=edge_widths,
        edge_color="#374151",
        alpha=0.75,
    )
    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=colours,
        node_size=sizes,
        alpha=0.9,
        linewidths=0.8,
        edgecolors="white",
    )

    legend_items = [
        mpatches.Patch(color="#ef4444", label="Locky-labelled input address"),
        mpatches.Patch(color="#111827", label="Bitcoin transaction"),
        mpatches.Patch(color="#f59e0b", label="Large output / possible hub"),
        mpatches.Patch(color="#93c5fd", label="Other output address"),
        mpatches.Patch(color="#d1d5db", label="Other input address"),
    ]
    ax.legend(handles=legend_items, loc="upper right", frameon=True)
    ax.set_title(title, fontsize=16, pad=16)
    ax.axis("off")
    plt.tight_layout()
    return fig


# -----------------------------
# App UI
# -----------------------------
st.title("Locky campaign-scale map")
st.caption("Exploratory large-scale view using Ransomwhere labels and Blockstream transaction data.")

st.markdown(
    """
    <div class="case-card">
    <h3>What this app does</h3>
    <p>
    This is a broader Locky mapping experiment. It starts from Locky-labelled addresses in the
    Ransomwhere dataset, fetches their Bitcoin transactions from Blockstream, then looks for
    shared-input transactions and large consolidation outputs.
    </p>
    <p class="small-note">
    This is exploratory. It can suggest patterns, but it does not prove real-world ownership.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Data source")
    json_path = st.text_input("Ransomwhere JSON path", DEFAULT_JSON_PATH)

    st.header("Candidate filter")
    min_balance_btc = st.number_input("Minimum Ransomwhere balance (BTC)", min_value=0.0, value=2.0, step=0.5)
    max_tx_count = st.number_input("Maximum Ransomwhere tx_count", min_value=1, value=3, step=1)
    max_addresses = st.slider("Maximum addresses to query", min_value=10, max_value=300, value=80, step=10)

    st.header("Graph filter")
    min_locky_inputs = st.number_input("Minimum Locky-labelled inputs per transaction", min_value=1, value=2, step=1)
    min_total_input_btc = st.number_input("Minimum total input BTC per transaction", min_value=0.0, value=10.0, step=5.0)
    max_transactions = st.slider("Maximum transactions in graph", min_value=1, max_value=50, value=12, step=1)
    max_outputs_per_tx = st.slider("Maximum outputs per transaction", min_value=1, max_value=10, value=3, step=1)

    st.divider()
    run_button = st.button("Build campaign map", type="primary")

try:
    df = load_ransomwhere_json(json_path)
except Exception as exc:
    st.error(str(exc))
    st.stop()

locky = df[df["family"] == "Locky"].copy()
locky_addresses = set(locky["address"].dropna().astype(str))

candidate_df = locky[
    (locky["balance_btc"] >= min_balance_btc)
    & (locky["tx_count"] <= max_tx_count)
].copy()

candidate_df = candidate_df.sort_values(["balance_btc", "tx_count"], ascending=[False, True]).head(max_addresses)
selected_addresses = candidate_df["address"].tolist()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Locky addresses in dataset", f"{len(locky):,}")
col2.metric("Selected candidates", f"{len(selected_addresses):,}")
col3.metric("Minimum BTC", f"{min_balance_btc:g}")
col4.metric("Max tx_count", f"{max_tx_count}")

with st.expander("Show selected candidate addresses", expanded=False):
    display_cols = ["address", "balance_btc", "tx_count", "balanceUSD"]
    available_cols = [c for c in display_cols if c in candidate_df.columns]
    st.dataframe(candidate_df[available_cols], use_container_width=True, hide_index=True)

if not run_button:
    st.info("Choose filters in the sidebar, then click **Build campaign map**.")
    st.stop()

if not selected_addresses:
    st.warning("No Locky candidates matched the current filters.")
    st.stop()

progress = st.progress(0)
status = st.empty()

try:
    df_inputs, df_outputs = build_campaign_data(selected_addresses, progress_bar=progress, status_text=status)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()

status.write("Finished fetching transactions.")
progress.progress(1.0)

if df_inputs.empty or df_outputs.empty:
    st.warning("No transaction data found for the selected addresses.")
    st.stop()

summary = summarise_transactions(df_inputs, df_outputs, locky_addresses)

st.subheader("Campaign transaction summary")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Unique transactions fetched", f"{summary['txid'].nunique():,}")
col2.metric("Strong Locky CIOH txs", f"{int(summary['strong_locky_cioh'].sum()):,}")
col3.metric("Largest Locky input count", f"{int(summary['locky_input_count'].max())}")
col4.metric("Largest total input", f"{summary['total_input_btc'].max():.4f} BTC")

st.markdown(
    """
    <div class="case-card">
    <h3>How to read this</h3>
    <p>
    A transaction with multiple Locky-labelled input addresses is useful for common-input ownership heuristic analysis.
    It suggests those addresses may have been controlled together, especially when the same transaction consolidates funds
    into one or two large outputs.
    </p>
    <p class="small-note">
    This remains a heuristic. Shared-input behaviour is a clue, not proof of a real-world identity.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

G = build_campaign_graph(
    df_inputs=df_inputs,
    df_outputs=df_outputs,
    locky_addresses=locky_addresses,
    min_locky_inputs=int(min_locky_inputs),
    min_total_input_btc=float(min_total_input_btc),
    max_transactions=int(max_transactions),
    max_outputs_per_tx=int(max_outputs_per_tx),
)

st.subheader("Campaign-scale graph")
st.pyplot(draw_campaign_graph(G, "Locky campaign-scale shared-input and consolidation map"))

st.subheader("Top shared-input / consolidation transactions")
summary_display = summary[
    [
        "txid",
        "input_count",
        "locky_input_count",
        "total_input_btc",
        "output_count",
        "largest_output_btc",
        "strong_locky_cioh",
    ]
].head(50)

st.dataframe(summary_display, use_container_width=True, hide_index=True)

with st.expander("Show full input table", expanded=False):
    st.dataframe(df_inputs, use_container_width=True, hide_index=True)

with st.expander("Show full output table", expanded=False):
    st.dataframe(df_outputs, use_container_width=True, hide_index=True)

# Optional download tables.
st.download_button(
    "Download transaction summary CSV",
    data=summary.to_csv(index=False).encode("utf-8"),
    file_name="locky_campaign_transaction_summary.csv",
    mime="text/csv",
)
