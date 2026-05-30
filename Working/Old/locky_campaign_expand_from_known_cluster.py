"""Locky campaign map: expand outward from a known 30-address CIOH cluster.

This Streamlit app starts from the verified Locky co-spend transaction where
30 Ransomwhere-labelled Locky addresses were used together as inputs and
about 80 BTC was consolidated into one output.

The goal is exploratory: keep the strong CIOH cluster as the anchor, then look
one step outward to see what the 80 BTC output did next.

Run:
    streamlit run locky_campaign_expand_from_known_cluster.py
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed case data
# -----------------------------
CASE_NAME = "Locky Campaign Map: Expansion from Known CIOH Cluster"

# Known 30-input Locky consolidation transaction
LOCKY_CIOH_TXID = "275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"

# The Locky-linked seed used in your case study
SEED_ADDRESS = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"

# 80 BTC output from the CIOH transaction
EIGHTY_BTC_ADDRESS = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"

# Follow-on 500 BTC consolidation transaction discovered from the 80 BTC address
FOLLOW_ON_TXID = "69affd84d73a7bbf644fe9defa18bab740b76487c07b636a6bb4a50689d8e8e3"

REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.2


# -----------------------------
# Helpers
# -----------------------------
def sats_to_btc(value: int | float | None) -> float:
    """Convert satoshis to BTC."""
    return (value or 0) / 100_000_000


def is_bitcoin_address(value: str) -> bool:
    """Simple check used only for graph styling."""
    return str(value).startswith(("1", "3", "bc1"))


def fetch_tx(txid: str) -> dict:
    """Fetch a single transaction from Blockstream."""
    url = f"https://blockstream.info/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(API_SLEEP_SECONDS)
    return response.json()


@st.cache_data(show_spinner=False)
def fetch_tx_cached(txid: str) -> dict:
    """Cached wrapper for fetching a transaction."""
    return fetch_tx(txid)


def extract_inputs_outputs(tx: dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return input and output tables for one transaction."""
    input_rows = []
    output_rows = []
    txid = tx["txid"]

    for i, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        input_rows.append({
            "Transaction ID": txid,
            "Input Index": i,
            "Input Address": prevout.get("scriptpubkey_address"),
            "Input BTC": sats_to_btc(prevout.get("value")),
        })

    for i, vout in enumerate(tx.get("vout", [])):
        output_rows.append({
            "Transaction ID": txid,
            "Output Index": i,
            "Output Address": vout.get("scriptpubkey_address"),
            "Output BTC": sats_to_btc(vout.get("value")),
        })

    return pd.DataFrame(input_rows), pd.DataFrame(output_rows)


def make_summary_table(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame,
                       follow_inputs: pd.DataFrame, follow_outputs: pd.DataFrame) -> pd.DataFrame:
    """Build a small narrative summary table."""
    cioh_total = cioh_inputs["Input BTC"].sum()
    follow_total = follow_inputs["Input BTC"].sum()

    main_output = cioh_outputs.sort_values("Output BTC", ascending=False).iloc[0]
    follow_main_output = follow_outputs.sort_values("Output BTC", ascending=False).iloc[0]

    rows = [
        {
            "Stage": "1. Known Locky co-spend",
            "What happened": "30 Ransomwhere-labelled Locky addresses were used as inputs in one transaction.",
            "BTC": f"{cioh_total:.8f}",
        },
        {
            "Stage": "2. Main consolidation output",
            "What happened": f"Most funds were sent to {main_output['Output Address']}.",
            "BTC": f"{main_output['Output BTC']:.8f}",
        },
        {
            "Stage": "3. Follow-on aggregation",
            "What happened": "The 80 BTC address later joined six other inputs in a larger transaction.",
            "BTC": f"{follow_total:.8f}",
        },
        {
            "Stage": "4. Larger output",
            "What happened": f"Most of the follow-on transaction was sent to {follow_main_output['Output Address']}.",
            "BTC": f"{follow_main_output['Output BTC']:.8f}",
        },
    ]
    return pd.DataFrame(rows)


# -----------------------------
# Graph builders
# -----------------------------
def build_campaign_graph(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame,
                         follow_inputs: pd.DataFrame, follow_outputs: pd.DataFrame) -> nx.DiGraph:
    """Build a graph from the known Locky cluster and the follow-on transaction."""
    G = nx.DiGraph()

    cioh_tx_node = "TX: Locky CIOH consolidation"
    follow_tx_node = "TX: follow-on 500 BTC consolidation"

    # 30 Locky-labelled inputs into CIOH tx
    for _, row in cioh_inputs.iterrows():
        addr = row["Input Address"]
        btc = row["Input BTC"]
        if pd.notna(addr):
            G.add_edge(addr, cioh_tx_node, btc=btc, edge_type="locky_input")

    # CIOH outputs
    for _, row in cioh_outputs.iterrows():
        addr = row["Output Address"]
        btc = row["Output BTC"]
        if pd.notna(addr):
            G.add_edge(cioh_tx_node, addr, btc=btc, edge_type="cioh_output")

    # Follow-on inputs
    for _, row in follow_inputs.iterrows():
        addr = row["Input Address"]
        btc = row["Input BTC"]
        if pd.notna(addr):
            G.add_edge(addr, follow_tx_node, btc=btc, edge_type="follow_input")

    # Follow-on outputs
    for _, row in follow_outputs.iterrows():
        addr = row["Output Address"]
        btc = row["Output BTC"]
        if pd.notna(addr):
            G.add_edge(follow_tx_node, addr, btc=btc, edge_type="follow_output")

    return G


def draw_campaign_graph(G: nx.DiGraph) -> plt.Figure:
    """Draw a SANS-style campaign expansion graph using the known cluster as anchor."""
    fig, ax = plt.subplots(figsize=(15, 9))

    # Spring layout keeps the dramatic network look.
    pos = nx.spring_layout(G, seed=42, k=0.95, iterations=90)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(900)
        elif node == EIGHTY_BTC_ADDRESS:
            node_colours.append("#111111")  # black
            node_sizes.append(980)
        elif str(node).startswith("TX:"):
            node_colours.append("#d1d5db")  # grey
            node_sizes.append(620)
        elif is_bitcoin_address(node):
            # Green if downstream output, blue otherwise.
            if G.in_degree(node) > 0 and G.out_degree(node) == 0:
                node_colours.append("#86efac")
                node_sizes.append(720)
            else:
                node_colours.append("#93c5fd")
                node_sizes.append(520)
        else:
            node_colours.append("#d1d5db")
            node_sizes.append(450)

    edge_widths = []
    for u, v, data in G.edges(data=True):
        btc = data.get("btc", 0)
        # Keep giant values visible but not absurd.
        edge_widths.append(max(0.8, min(5.5, btc / 25)))

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_color=node_colours,
        node_size=node_sizes,
        width=edge_widths,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
        alpha=0.88,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#93c5fd", label="Locky-labelled input address"),
        mpatches.Patch(color="#111111", label="80 BTC consolidation address"),
        mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
        mpatches.Patch(color="#86efac", label="Follow-on output address"),
    ]
    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Campaign expansion from the known Locky CIOH cluster", pad=18)
    ax.axis("off")
    return fig


def build_cioh_only_graph(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame) -> nx.DiGraph:
    """Build focused graph for the initial CIOH event only."""
    G = nx.DiGraph()
    tx_node = "TX: shared-input transaction"

    for _, row in cioh_inputs.iterrows():
        G.add_edge(row["Input Address"], tx_node, btc=row["Input BTC"])

    for _, row in cioh_outputs.iterrows():
        G.add_edge(tx_node, row["Output Address"], btc=row["Output BTC"])

    return G


def draw_cioh_graph(G: nx.DiGraph) -> plt.Figure:
    """Draw the clean CIOH anchor graph."""
    fig, ax = plt.subplots(figsize=(14, 8))
    pos = nx.spring_layout(G, seed=7, k=0.82, iterations=80)

    colours = []
    sizes = []
    for node in G.nodes():
        if node == SEED_ADDRESS:
            colours.append("#ef4444")
            sizes.append(850)
        elif node == EIGHTY_BTC_ADDRESS:
            colours.append("#111111")
            sizes.append(950)
        elif str(node).startswith("TX:"):
            colours.append("#d1d5db")
            sizes.append(650)
        elif is_bitcoin_address(node):
            colours.append("#93c5fd")
            sizes.append(520)
        else:
            colours.append("#d1d5db")
            sizes.append(450)

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_color=colours,
        node_size=sizes,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
        width=1.8,
        alpha=0.88,
    )

    ax.legend(
        handles=[
            mpatches.Patch(color="#ef4444", label="Seed address"),
            mpatches.Patch(color="#93c5fd", label="Locky-labelled input address"),
            mpatches.Patch(color="#d1d5db", label="Shared Bitcoin transaction"),
            mpatches.Patch(color="#111111", label="80 BTC consolidation address"),
        ],
        loc="best",
    )
    ax.set_title("Known Locky CIOH event", pad=18)
    ax.axis("off")
    return fig


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(
    page_title=CASE_NAME,
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
st.title(CASE_NAME)
st.caption("Exploratory view. The first transaction is the strong Locky CIOH evidence; the follow-on transaction is traced movement with uncertain attribution.")

with st.spinner("Fetching Bitcoin transactions from Blockstream..."):
    try:
        cioh_tx = fetch_tx_cached(LOCKY_CIOH_TXID)
        follow_tx = fetch_tx_cached(FOLLOW_ON_TXID)
    except requests.exceptions.RequestException as exc:
        st.error(f"Could not fetch data from Blockstream: {exc}")
        st.stop()

cioh_inputs, cioh_outputs = extract_inputs_outputs(cioh_tx)
follow_inputs, follow_outputs = extract_inputs_outputs(follow_tx)

cioh_total = cioh_inputs["Input BTC"].sum()
follow_total = follow_inputs["Input BTC"].sum()
main_cioh_output = cioh_outputs.sort_values("Output BTC", ascending=False).iloc[0]
main_follow_output = follow_outputs.sort_values("Output BTC", ascending=False).iloc[0]

st.markdown(
    """
    <div class="case-card">
    <h3>What this map shows</h3>
    <p>
    This view starts from the known Locky shared-input transaction, where 30 Locky-labelled addresses were used together.
    It then traces the 80 BTC output into one later aggregation transaction.
    </p>
    <p class="small-note">
    The first transaction is the strong CIOH case. The later aggregation is useful tracing evidence, but those later addresses are not labelled in the ransomware dataset.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Locky-labelled inputs", len(cioh_inputs))
col2.metric("CIOH transaction total", f"{cioh_total:.8f} BTC")
col3.metric("Main CIOH output", f"{main_cioh_output['Output BTC']:.8f} BTC")
col4.metric("Follow-on total", f"{follow_total:.8f} BTC")
col5.metric("Largest follow-on output", f"{main_follow_output['Output BTC']:.8f} BTC")

st.subheader("1. Known Locky CIOH event")
st.write("These 30 Locky-labelled addresses were used together as inputs in one Bitcoin transaction. This is the main common-input ownership heuristic example.")
cioh_graph = build_cioh_only_graph(cioh_inputs, cioh_outputs)
st.pyplot(draw_cioh_graph(cioh_graph))

st.subheader("2. Campaign expansion from the known cluster")
st.write("The 80 BTC output later joined six other inputs in a larger aggregation transaction. Attribution for this later step is uncertain because those later input addresses were not labelled in the ransomware dataset.")
campaign_graph = build_campaign_graph(cioh_inputs, cioh_outputs, follow_inputs, follow_outputs)
st.pyplot(draw_campaign_graph(campaign_graph))

st.subheader("Summary")
st.dataframe(make_summary_table(cioh_inputs, cioh_outputs, follow_inputs, follow_outputs), use_container_width=True, hide_index=True)

st.subheader("Transaction tables")

with st.expander("CIOH transaction inputs — full addresses"):
    st.dataframe(
        cioh_inputs[["Input Address", "Input BTC"]].sort_values("Input BTC", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with st.expander("CIOH transaction outputs — full addresses"):
    st.dataframe(
        cioh_outputs[["Output Address", "Output BTC"]].sort_values("Output BTC", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with st.expander("Follow-on transaction inputs — full addresses"):
    st.dataframe(
        follow_inputs[["Input Address", "Input BTC"]].sort_values("Input BTC", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with st.expander("Follow-on transaction outputs — full addresses"):
    st.dataframe(
        follow_outputs[["Output Address", "Output BTC"]].sort_values("Output BTC", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Method note")
st.markdown(
    """
    The common-input ownership heuristic groups addresses that are used together as inputs in one transaction.
    In this case, the first transaction is strong because all 30 inputs are labelled Locky in the ransomware dataset.

    The follow-on transaction is shown as tracing context only. It shows where the 80 BTC consolidation output moved next,
    but the later addresses are not independently labelled in the ransomware dataset, so ownership should not be overclaimed.
    """
)
