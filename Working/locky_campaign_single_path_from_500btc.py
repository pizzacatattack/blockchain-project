"""Locky campaign map: single-path trace from the known CIOH cluster.

This Streamlit app keeps the strong Locky CIOH case as the anchor:
30 Ransomwhere-labelled Locky addresses were co-spent in one transaction,
consolidating about 80 BTC.

It then follows the main consolidation path:
80 BTC output -> 500 BTC output -> largest later output(s), one hop at a time.

Run:
    streamlit run locky_campaign_single_path_from_500btc.py
"""

import time
from typing import Dict, List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed Locky case data
# -----------------------------
CASE_NAME = "Locky Campaign Map: Single-Path Expansion"

LOCKY_CIOH_TXID = "275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"
FOLLOW_ON_TXID = "69affd84d73a7bbf644fe9defa18bab740b76487c07b636a6bb4a50689d8e8e3"

SEED_ADDRESS = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"
EIGHTY_BTC_ADDRESS = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"
FIVE_HUNDRED_BTC_ADDRESS = "16YhEbMcksa6zgf2rjcAUWy7fZ9TkgFNXF"

REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.15


# -----------------------------
# Helper functions
# -----------------------------
def sats_to_btc(value) -> float:
    """Convert satoshis to BTC."""
    return (value or 0) / 100_000_000


def is_bitcoin_address(value: str) -> bool:
    """Simple check used only for graph styling."""
    return str(value).startswith(("1", "3", "bc1"))


@st.cache_data(show_spinner=False)
def fetch_tx(txid: str) -> dict:
    """Fetch one Bitcoin transaction from Blockstream."""
    url = f"https://blockstream.info/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(API_SLEEP_SECONDS)
    return response.json()


@st.cache_data(show_spinner=False)
def fetch_address_txs(address: str) -> List[dict]:
    """Fetch confirmed transactions for an address from Blockstream."""
    url = f"https://blockstream.info/api/address/{address}/txs/chain"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(API_SLEEP_SECONDS)
    return response.json()


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


def find_spend_transaction(address: str) -> Optional[dict]:
    """Find the transaction where the address is spent as an input.

    If there are multiple spends, return the one where the address contributes the
    most BTC. For normal single-use addresses, this is just the only spend.
    """
    txs = fetch_address_txs(address)
    best_tx = None
    best_value = 0.0

    for tx in txs:
        value_from_address = 0.0
        for vin in tx.get("vin", []):
            prevout = vin.get("prevout") or {}
            if prevout.get("scriptpubkey_address") == address:
                value_from_address += sats_to_btc(prevout.get("value"))

        if value_from_address > best_value:
            best_tx = tx
            best_value = value_from_address

    return best_tx


def choose_largest_output(tx: dict, exclude_address: Optional[str] = None) -> Optional[dict]:
    """Choose the largest output address from a transaction."""
    outputs = []
    for i, vout in enumerate(tx.get("vout", [])):
        address = vout.get("scriptpubkey_address")
        value = sats_to_btc(vout.get("value"))
        if address and address != exclude_address:
            outputs.append({
                "Output Index": i,
                "Output Address": address,
                "Output BTC": value,
            })

    if not outputs:
        return None

    return max(outputs, key=lambda row: row["Output BTC"])


@st.cache_data(show_spinner=False)
def trace_largest_output_path(start_address: str, max_hops: int) -> pd.DataFrame:
    """Trace the largest-output path starting from a given address.

    Each hop finds where the current address is spent, then follows the largest
    output from that transaction.
    """
    rows = []
    current_address = start_address
    seen_addresses = set()

    for hop in range(1, max_hops + 1):
        if current_address in seen_addresses:
            rows.append({
                "Hop": hop,
                "From Address": current_address,
                "Spend Transaction ID": "Stopped: loop detected",
                "Input From Address BTC": None,
                "Total Transaction Input BTC": None,
                "Next Address": None,
                "Next Output BTC": None,
                "Note": "Loop detected",
            })
            break

        seen_addresses.add(current_address)
        spend_tx = find_spend_transaction(current_address)

        if spend_tx is None:
            rows.append({
                "Hop": hop,
                "From Address": current_address,
                "Spend Transaction ID": "No spend found",
                "Input From Address BTC": None,
                "Total Transaction Input BTC": None,
                "Next Address": None,
                "Next Output BTC": None,
                "Note": "Address has not been spent in fetched confirmed transactions",
            })
            break

        inputs, outputs = extract_inputs_outputs(spend_tx)
        from_value = inputs.loc[inputs["Input Address"] == current_address, "Input BTC"].sum()
        total_input = inputs["Input BTC"].sum()
        largest_output = choose_largest_output(spend_tx, exclude_address=current_address)

        if largest_output is None:
            rows.append({
                "Hop": hop,
                "From Address": current_address,
                "Spend Transaction ID": spend_tx["txid"],
                "Input From Address BTC": from_value,
                "Total Transaction Input BTC": total_input,
                "Next Address": None,
                "Next Output BTC": None,
                "Note": "No usable output address found",
            })
            break

        rows.append({
            "Hop": hop,
            "From Address": current_address,
            "Spend Transaction ID": spend_tx["txid"],
            "Input From Address BTC": from_value,
            "Total Transaction Input BTC": total_input,
            "Next Address": largest_output["Output Address"],
            "Next Output BTC": largest_output["Output BTC"],
            "Note": "Following largest output",
        })

        current_address = largest_output["Output Address"]

    return pd.DataFrame(rows)


# -----------------------------
# Graph builders
# -----------------------------
def build_cioh_graph(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame) -> nx.DiGraph:
    """Build focused graph for the initial CIOH event."""
    G = nx.DiGraph()
    tx_node = "TX: 30 Locky inputs"

    for _, row in cioh_inputs.iterrows():
        G.add_edge(row["Input Address"], tx_node, btc=row["Input BTC"], edge_type="locky_input")

    for _, row in cioh_outputs.iterrows():
        G.add_edge(tx_node, row["Output Address"], btc=row["Output BTC"], edge_type="cioh_output")

    return G


def build_single_path_graph(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame,
                            follow_inputs: pd.DataFrame, follow_outputs: pd.DataFrame,
                            path_df: pd.DataFrame) -> nx.DiGraph:
    """Build graph from CIOH event, follow-on tx, and largest-output path."""
    G = build_cioh_graph(cioh_inputs, cioh_outputs)
    follow_tx_node = "TX: 512.999 BTC aggregation"

    # Add the known 80 -> 500 BTC aggregation transaction.
    for _, row in follow_inputs.iterrows():
        G.add_edge(row["Input Address"], follow_tx_node, btc=row["Input BTC"], edge_type="follow_input")

    for _, row in follow_outputs.iterrows():
        G.add_edge(follow_tx_node, row["Output Address"], btc=row["Output BTC"], edge_type="follow_output")

    # Add later strict single path from 500 BTC address.
    for _, row in path_df.iterrows():
        txid = row.get("Spend Transaction ID")
        next_address = row.get("Next Address")
        if pd.isna(txid) or txid in ["No spend found", "Stopped: loop detected"] or not isinstance(txid, str):
            continue
        if pd.isna(next_address) or not isinstance(next_address, str):
            continue

        tx_node = f"TX: hop {int(row['Hop'])}"
        from_address = row["From Address"]
        G.add_edge(from_address, tx_node, btc=row.get("Input From Address BTC") or 0, edge_type="path_input")
        G.add_edge(tx_node, next_address, btc=row.get("Next Output BTC") or 0, edge_type="path_output")

    return G


def draw_graph(G: nx.DiGraph, title: str) -> plt.Figure:
    """Draw campaign graph."""
    fig, ax = plt.subplots(figsize=(16, 9))
    pos = nx.spring_layout(G, seed=42, k=0.9, iterations=100)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")
            node_sizes.append(900)
        elif node == EIGHTY_BTC_ADDRESS:
            node_colours.append("#111111")
            node_sizes.append(950)
        elif node == FIVE_HUNDRED_BTC_ADDRESS:
            node_colours.append("#f59e0b")
            node_sizes.append(1050)
        elif str(node).startswith("TX:"):
            node_colours.append("#d1d5db")
            node_sizes.append(650)
        elif is_bitcoin_address(node):
            # Later traced addresses: green if they are outputs only.
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
    for _, _, data in G.edges(data=True):
        btc = data.get("btc") or 0
        edge_widths.append(max(0.8, min(6.0, btc / 40)))

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

    ax.legend(
        handles=[
            mpatches.Patch(color="#ef4444", label="Seed address"),
            mpatches.Patch(color="#93c5fd", label="Locky-labelled input / later input"),
            mpatches.Patch(color="#111111", label="80 BTC consolidation address"),
            mpatches.Patch(color="#f59e0b", label="500 BTC address"),
            mpatches.Patch(color="#86efac", label="Later largest-output address"),
            mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
        ],
        loc="best",
    )
    ax.set_title(title, pad=18)
    ax.axis("off")
    return fig


def make_summary(cioh_inputs: pd.DataFrame, cioh_outputs: pd.DataFrame,
                 follow_inputs: pd.DataFrame, follow_outputs: pd.DataFrame,
                 path_df: pd.DataFrame) -> pd.DataFrame:
    """Build compact summary table."""
    rows = []
    cioh_main = cioh_outputs.sort_values("Output BTC", ascending=False).iloc[0]
    follow_main = follow_outputs.sort_values("Output BTC", ascending=False).iloc[0]

    rows.append({
        "Stage": "1. Locky CIOH cluster",
        "What happened": "30 Locky-labelled addresses were co-spent in one transaction.",
        "BTC": f"{cioh_inputs['Input BTC'].sum():.8f}",
        "Address": "Multiple Locky-labelled input addresses",
    })
    rows.append({
        "Stage": "2. 80 BTC consolidation",
        "What happened": "Most funds from the Locky CIOH transaction went to one address.",
        "BTC": f"{cioh_main['Output BTC']:.8f}",
        "Address": cioh_main["Output Address"],
    })
    rows.append({
        "Stage": "3. 500 BTC aggregation",
        "What happened": "The 80 BTC address later joined six other inputs in a larger transaction.",
        "BTC": f"{follow_main['Output BTC']:.8f}",
        "Address": follow_main["Output Address"],
    })

    for _, row in path_df.iterrows():
        rows.append({
            "Stage": f"4.{int(row['Hop'])} Largest-output trace hop {int(row['Hop'])}",
            "What happened": "Followed the largest output from the current address.",
            "BTC": "" if pd.isna(row["Next Output BTC"]) else f"{row['Next Output BTC']:.8f}",
            "Address": "" if pd.isna(row["Next Address"]) else row["Next Address"],
        })

    return pd.DataFrame(rows)


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title=CASE_NAME, page_icon="₿", layout="wide")

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
st.caption("Exploratory campaign view. Strong attribution is only claimed for the initial Locky-labelled CIOH transaction.")

with st.sidebar:
    st.header("Trace settings")
    max_hops = st.slider("Largest-output hops after the 500 BTC address", min_value=1, max_value=5, value=3)
    st.caption("This follows only the largest output each hop to avoid graph chaos.")

with st.spinner("Fetching Bitcoin transactions from Blockstream..."):
    try:
        cioh_tx = fetch_tx(LOCKY_CIOH_TXID)
        follow_tx = fetch_tx(FOLLOW_ON_TXID)
        path_df = trace_largest_output_path(FIVE_HUNDRED_BTC_ADDRESS, max_hops=max_hops)
    except requests.exceptions.RequestException as exc:
        st.error(f"Could not fetch data from Blockstream: {exc}")
        st.stop()

cioh_inputs, cioh_outputs = extract_inputs_outputs(cioh_tx)
follow_inputs, follow_outputs = extract_inputs_outputs(follow_tx)
main_cioh_output = cioh_outputs.sort_values("Output BTC", ascending=False).iloc[0]
main_follow_output = follow_outputs.sort_values("Output BTC", ascending=False).iloc[0]

st.markdown(
    """
    <div class="case-card">
    <h3>What this map shows</h3>
    <p>
    This map starts from the strong Locky common-input ownership heuristic event: 30 Locky-labelled addresses were used together as inputs.
    It then follows the main output path: 80 BTC moved into a larger 512.999 BTC aggregation, which produced a 500 BTC output.
    The app then follows only the largest output from the 500 BTC address for a small number of hops.
    </p>
    <p class="small-note">
    Later hops are tracing context only. They are not independently labelled as Locky in the ransomware dataset, so attribution should not be overclaimed.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Locky-labelled inputs", len(cioh_inputs))
col2.metric("CIOH total", f"{cioh_inputs['Input BTC'].sum():.8f} BTC")
col3.metric("80 BTC output", f"{main_cioh_output['Output BTC']:.8f} BTC")
col4.metric("Follow-on total", f"{follow_inputs['Input BTC'].sum():.8f} BTC")
col5.metric("500 BTC output", f"{main_follow_output['Output BTC']:.8f} BTC")

st.subheader("1. Known Locky CIOH event")
st.write("These 30 Locky-labelled addresses were used together as inputs in one Bitcoin transaction.")
st.pyplot(draw_graph(build_cioh_graph(cioh_inputs, cioh_outputs), "Known Locky CIOH event"))

st.subheader("2. Single-path campaign expansion")
st.write("This graph follows the main path: 80 BTC output → 500 BTC output → largest later outputs.")
full_graph = build_single_path_graph(cioh_inputs, cioh_outputs, follow_inputs, follow_outputs, path_df)
st.pyplot(draw_graph(full_graph, "Single-path expansion from the 500 BTC address"))

st.subheader("Summary")
st.dataframe(make_summary(cioh_inputs, cioh_outputs, follow_inputs, follow_outputs, path_df), use_container_width=True, hide_index=True)

st.subheader("Largest-output trace table")
st.dataframe(path_df, use_container_width=True, hide_index=True)

st.subheader("Transaction tables")
with st.expander("Initial CIOH inputs — full addresses"):
    st.dataframe(cioh_inputs.sort_values("Input BTC", ascending=False), use_container_width=True, hide_index=True)

with st.expander("Initial CIOH outputs — full addresses"):
    st.dataframe(cioh_outputs.sort_values("Output BTC", ascending=False), use_container_width=True, hide_index=True)

with st.expander("500 BTC aggregation inputs — full addresses"):
    st.dataframe(follow_inputs.sort_values("Input BTC", ascending=False), use_container_width=True, hide_index=True)

with st.expander("500 BTC aggregation outputs — full addresses"):
    st.dataframe(follow_outputs.sort_values("Output BTC", ascending=False), use_container_width=True, hide_index=True)

st.subheader("Method note")
st.markdown(
    """
    The initial transaction is the strongest evidence in this view because all 30 inputs are labelled Locky in the ransomware dataset
    and were co-spent in one transaction. That is the common-input ownership heuristic example.

    The later path is exploratory tracing. It follows the largest output after the 500 BTC address, but later addresses are not
    independently labelled in the ransomware dataset. Treat them as movement context, not confirmed Locky ownership.
    """
)
