"""
ChipMixer-style CoinJoin Case Study

This Streamlit app starts from a ChipMixer-linked coordinator-fee style address
from the paper "An Empirical Analysis of Privacy in the Lightning Network"
that was previously discussed by the user.

The goal is to find and display one transaction with strong mixer/CoinJoin-like
structure:
- many inputs
- many outputs
- repeated or similar output amounts
- weak direct mapping between a specific input and a specific output

This is a fixed case-study app, not a general address explorer.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed case settings
# -----------------------------
CASE_NAME = "ChipMixer CoinJoin-Style Case Study"

# Address discussed earlier as appearing in thousands of CoinJoin transactions.
SEED_ADDRESS = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"

BACKUP_ADDRESS = "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw"

REQUEST_TIMEOUT_SECONDS = 20
SATOSHIS_PER_BTC = 100_000_000
MAX_ADDRESS_PAGES = 6

MAX_GRAPH_INPUTS = 14
MAX_GRAPH_OUTPUTS = 18

BLOCKSTREAM_URL = "https://blockstream.info"


# -----------------------------
# Page setup
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


# -----------------------------
# Helpers
# -----------------------------
def sats_to_btc(value: Optional[int]) -> float:
    if value is None:
        return 0.0
    return value / SATOSHIS_PER_BTC


def btc(value: float) -> str:
    return f"{value:.8f} BTC"


def short_hash(value: str) -> str:
    if not value:
        return "Unknown"
    if len(value) <= 14:
        return value
    return f"{value[:6]}…{value[-6:]}"


def format_date(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "Unknown"
    return datetime.utcfromtimestamp(timestamp).strftime("%d %b %Y")


def safe_address(vout: Dict[str, Any]) -> Optional[str]:
    return vout.get("scriptpubkey_address")


@st.cache_data(show_spinner=False)
def get_address_info(address: str) -> Dict[str, Any]:
    url = f"{BLOCKSTREAM_URL}/api/address/{address}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def get_address_transactions(address: str, max_pages: int = MAX_ADDRESS_PAGES) -> List[Dict[str, Any]]:
    all_txs: List[Dict[str, Any]] = []
    last_seen = None

    for _ in range(max_pages):
        if last_seen:
            url = f"{BLOCKSTREAM_URL}/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"{BLOCKSTREAM_URL}/api/address/{address}/txs/chain"

        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        all_txs.extend(data)

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.25)

    return all_txs


def get_input_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        address = prevout.get("scriptpubkey_address")
        value_btc = sats_to_btc(prevout.get("value", 0))

        rows.append({
            "Input Index": index,
            "Input Address": address,
            "Input BTC": value_btc,
            "Seed Address Input": address == SEED_ADDRESS,
        })
    return rows


def get_output_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vout in enumerate(tx.get("vout", [])):
        address = safe_address(vout)
        value_btc = sats_to_btc(vout.get("value", 0))

        rows.append({
            "Output Index": index,
            "Output Address": address,
            "Output BTC": value_btc,
            "Seed Address Output": address == SEED_ADDRESS,
        })
    return rows


def repeated_output_summary(outputs: List[Dict[str, Any]], decimals: int = 8) -> pd.DataFrame:
    """Group output values to detect repeated denominations."""
    if not outputs:
        return pd.DataFrame(columns=["Rounded Output BTC", "Count", "Total BTC"])

    df = pd.DataFrame(outputs)
    df["Rounded Output BTC"] = df["Output BTC"].round(decimals)

    grouped = (
        df.groupby("Rounded Output BTC", dropna=False)
        .agg(Count=("Output BTC", "count"), Total_BTC=("Output BTC", "sum"))
        .reset_index()
        .rename(columns={"Total_BTC": "Total BTC"})
        .sort_values(["Count", "Total BTC"], ascending=False)
        .reset_index(drop=True)
    )

    return grouped


def transaction_score(tx: Dict[str, Any]) -> float:
    """Score transactions for visually strong CoinJoin/mixer-like structure."""
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    input_count = len(inputs)
    output_count = len(outputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)

    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_outputs = repeated_df[repeated_df["Count"] >= 2]
    max_repeat_count = int(repeated_df["Count"].max()) if not repeated_df.empty else 0

    seed_involved = any(row["Seed Address Input"] for row in inputs) or any(row["Seed Address Output"] for row in outputs)

    score = 0

    # CoinJoin-like transactions are visually stronger with many inputs and outputs.
    score += input_count * 6
    score += output_count * 8

    # Repeated output amounts are very important for a CoinJoin-style explanation.
    score += max_repeat_count * 25
    score += len(repeated_outputs) * 30

    # Avoid tiny/noisy transactions being selected just because they have repeats.
    score += min(total_output_btc, 50) * 0.4

    if seed_involved:
        score += 60

    # Penalise boring simple transactions.
    if input_count <= 2 or output_count <= 2:
        score -= 100

    if output_count < 5:
        score -= 60

    return score


def choose_case_transaction(address: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch transactions and select the most compelling mixer-like transaction."""
    info = get_address_info(address)
    txs = get_address_transactions(address, max_pages=MAX_ADDRESS_PAGES)

    if not txs:
        raise ValueError("No transactions were found for the ChipMixer-linked address.")

    best_tx = max(txs, key=transaction_score)
    return info, best_tx, txs


def build_address_summary(address: str, info: Dict[str, Any], txs: List[Dict[str, Any]]) -> pd.DataFrame:
    chain_stats = info.get("chain_stats", {})
    funded_btc = sats_to_btc(chain_stats.get("funded_txo_sum", 0))
    spent_btc = sats_to_btc(chain_stats.get("spent_txo_sum", 0))

    rows = [
        {"Metric": "ChipMixer-linked seed address", "Value": address},
        {"Metric": "Fetched transactions analysed", "Value": len(txs)},
        {"Metric": "Confirmed transaction count", "Value": chain_stats.get("tx_count", 0)},
        {"Metric": "Confirmed BTC received", "Value": btc(funded_btc)},
        {"Metric": "Confirmed BTC spent", "Value": btc(spent_btc)},
    ]
    return pd.DataFrame(rows)


def build_transaction_summary(tx: Dict[str, Any]) -> pd.DataFrame:
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    total_input_btc = sum(row["Input BTC"] for row in inputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)
    fee_btc = sats_to_btc(tx.get("fee", 0))

    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_values = repeated_df[repeated_df["Count"] >= 2]
    max_repeat = int(repeated_df["Count"].max()) if not repeated_df.empty else 0

    rows = [
        {"Metric": "Selected transaction", "Value": tx.get("txid")},
        {"Metric": "Date", "Value": format_date(tx.get("status", {}).get("block_time"))},
        {"Metric": "Input count", "Value": len(inputs)},
        {"Metric": "Output count", "Value": len(outputs)},
        {"Metric": "Total input BTC", "Value": btc(total_input_btc)},
        {"Metric": "Total output BTC", "Value": btc(total_output_btc)},
        {"Metric": "Transaction fee", "Value": btc(fee_btc)},
        {"Metric": "Repeated output values detected", "Value": len(repeated_values)},
        {"Metric": "Largest repeated output group", "Value": max_repeat},
    ]
    return pd.DataFrame(rows)


def draw_coinjoin_structure_graph(tx: Dict[str, Any]) -> plt.Figure:
    """Draw a dramatic many-to-many mixer-style graph."""
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    inputs_sorted = sorted(inputs, key=lambda row: row["Input BTC"], reverse=True)
    outputs_sorted = sorted(outputs, key=lambda row: row["Output BTC"], reverse=True)

    # Show fewer sample inputs so the graph is cleaner
    shown_inputs = inputs_sorted[:10]
    shown_outputs = outputs_sorted[:18]

    other_input_btc = sum(row["Input BTC"] for row in inputs_sorted[10:])
    other_output_btc = sum(row["Output BTC"] for row in outputs_sorted[18:])

    G = nx.DiGraph()

    pos = {}
    labels = {}

    pool_node = "Shared pool"

    # -------------------------
    # INPUT SIDE
    # -------------------------
    for i, row in enumerate(shown_inputs):
        node = f"Input {i}"
        G.add_edge(node, pool_node)

        y = ((len(shown_inputs)) / 2) - i
        pos[node] = (-3.6, y * 0.7)

        labels[node] = "Sample input"

    other_input_node = "Other inputs"
    G.add_edge(other_input_node, pool_node)
    pos[other_input_node] = (-3.6, -4.8)
    labels[other_input_node] = f"{len(inputs) - 10} other inputs"

    # -------------------------
    # POOL
    # -------------------------
    pos[pool_node] = (0, 0)
    total_input_btc = sum(row["Input BTC"] for row in inputs)

    labels[pool_node] = (
        f"Shared pool\n"
        f"{len(inputs)} inputs\n"
        f"{total_input_btc:.1f} BTC"
    )

    # -------------------------
    # OUTPUT SIDE
    # -------------------------
    output_values = pd.Series([row["Output BTC"] for row in outputs]).round(8)
    repeated_values = set(
        output_values.value_counts()[output_values.value_counts() >= 2].index
    )

    for i, row in enumerate(shown_outputs):
        node = f"Output {i}"
        G.add_edge(pool_node, node)

        y = ((len(shown_outputs)) / 2) - i
        pos[node] = (3.8, y * 0.6)

        value = round(row["Output BTC"], 8)

        if value in repeated_values:
            labels[node] = f"{value:.4f} BTC\n(repeated)"
        else:
            labels[node] = f"{value:.4f} BTC"

    other_output_node = "Other outputs"
    G.add_edge(pool_node, other_output_node)
    pos[other_output_node] = (3.8, -6.4)
    labels[other_output_node] = f"{other_output_btc:.1f} BTC\nother outputs"

    # -------------------------
    # COLOURS
    # -------------------------
    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == pool_node:
            node_colours.append("#9ca3af")
            node_sizes.append(2600)

        elif node.startswith("Input") or node == other_input_node:
            node_colours.append("#93c5fd")
            node_sizes.append(1200)

        elif node == other_output_node:
            node_colours.append("#86efac")
            node_sizes.append(1400)

        else:
            output_index = int(node.split(" ")[1])
            value = round(shown_outputs[output_index]["Output BTC"], 8)

            if value in repeated_values:
                node_colours.append("#22c55e")
                node_sizes.append(1500)
            else:
                node_colours.append("#86efac")
                node_sizes.append(1300)

    fig, ax = plt.subplots(figsize=(15, 10))

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_color=node_colours,
        node_size=node_sizes,
        edge_color="#6b7280",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=14,
        width=1.3,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=7,
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color="#93c5fd", label="Pooled input side"),
        mpatches.Patch(color="#9ca3af", label="Shared transaction"),
        mpatches.Patch(color="#22c55e", label="Repeated output denomination"),
        mpatches.Patch(color="#86efac", label="Other output"),
    ]

    ax.legend(handles=legend_handles, loc="upper right")

    ax.set_title(
        "Mixer-style transaction with repeated output denominations",
        fontsize=14,
        pad=18,
    )

    ax.axis("off")
    fig.tight_layout()

    return fig

   



# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A Bitcoin tracing case study showing how mixer/CoinJoin-style transactions weaken direct ownership tracing.")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
            This case starts from a ChipMixer-linked address discussed in research as appearing in thousands
            of CoinJoin transactions. The app searches that address transaction history and selects a transaction
            with strong CoinJoin-style structure.
        </p>
        <p>
            The focus is not to prove the owner of every address. The focus is to show how many-input,
            many-output transactions with repeated output values can make simple tracing and common-input
            ownership assumptions unreliable.
        </p>
        <p>
            Seed address: <code>{SEED_ADDRESS}</code>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.header("Why this matters for tracing")
st.markdown(
    """
    <div class="case-card">
        <p>
            In basic Bitcoin tracing, analysts may look at transaction inputs and outputs to infer who controlled
            which funds. Mixer and CoinJoin-style transactions are designed to disrupt that logic.
        </p>
        <p>
            When a transaction combines many inputs and creates many similar outputs, it becomes harder to map
            one input to one output. It also weakens the common-input ownership heuristic, because the inputs may
            come from different participants rather than one wallet.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading ChipMixer-linked transaction data from Blockstream..."):
        address_info, selected_tx, address_txs = choose_case_transaction(SEED_ADDRESS)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()
except Exception as exc:
    st.error(f"Case loading failed: {exc}")
    st.stop()

inputs = get_input_rows(selected_tx)
outputs = get_output_rows(selected_tx)
repeated_df = repeated_output_summary(outputs, decimals=8)
repeated_values = repeated_df[repeated_df["Count"] >= 2]
total_output_btc = sum(row["Output BTC"] for row in outputs)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Transactions analysed", len(address_txs))
col2.metric("Transaction inputs", len(inputs))
col3.metric("Transaction outputs", len(outputs))
col4.metric("Repeated output groups", len(repeated_values))
col5.metric("Total output BTC", f"{total_output_btc:.4f}")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Key finding</h3>
        <p>
            The selected transaction contains <strong>{len(inputs)} inputs</strong> and
            <strong>{len(outputs)} outputs</strong>, showing pooled movement rather than a simple payment.
        </p>
        <p>
            The strongest signal is the repeated output denominations. The app detected
            <strong>{len(repeated_values)} repeated output value groups</strong>, including standard-sized
            chunks that appear many times across different output addresses.
        </p>
        <p>
            This matters because repeated output sizes make it harder to directly match one input participant
            to one output recipient. A participant may receive value back as several smaller standard-sized outputs,
            rather than as one neat output.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Mixer-style transaction graph")
st.write(
    "This graph summarises the selected transaction. Instead of showing every individual address, it shows "
    "the input side as a pooled group and highlights the repeated output denominations on the right. "
    "This makes the mixer-style structure easier to read."
)
st.pyplot(draw_coinjoin_structure_graph(selected_tx), use_container_width=True)

st.subheader("2. Selected transaction summary")
st.dataframe(build_transaction_summary(selected_tx), use_container_width=True, hide_index=True)

st.subheader("3. Repeated output value summary (key evidence)")
st.write(
    "This table is the strongest evidence in this case. It shows that many outputs were created with the same BTC amounts, "
    "which is consistent with funds being redistributed in standard-sized chunks rather than following a simple one-to-one path."
)
st.dataframe(repeated_df.head(20), use_container_width=True, hide_index=True)

st.subheader("4. Address summary")
st.dataframe(build_address_summary(SEED_ADDRESS, address_info, address_txs), use_container_width=True, hide_index=True)

with st.expander("Show selected transaction inputs and outputs"):
    st.markdown("**Inputs**")
    st.dataframe(pd.DataFrame(inputs), use_container_width=True, hide_index=True)

    st.markdown("**Outputs**")
    st.dataframe(pd.DataFrame(outputs), use_container_width=True, hide_index=True)

st.subheader("Interpretation note")
st.markdown(
    """
    <div class="case-card">
        <p>
            Blockchain tracing shows transaction movement, not real-world identity. In this case, the graph
            highlights structure: many inputs, many outputs and repeated output values. These are tracing
            complications rather than proof of who controlled each address.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("References")
with st.expander("Show references and data sources"):
    st.markdown(
        """
        Blockstream (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/explorer-api.

        U.S. Department of Justice (2023) *ChipMixer domain seized by law enforcement*. Available at: https://www.justice.gov/opa/pr/chipmixer-domain-seized-law-enforcement.

        Europol (2023) *ChipMixer taken down for laundering criminal proceeds*. Available at: https://www.europol.europa.eu/media-press/newsroom/news/multi-billion-euro-crypto-laundering-service-chipmixer-taken-down.
        """
    )
