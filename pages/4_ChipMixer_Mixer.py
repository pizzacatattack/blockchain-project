"""
ChipMixer Mixer Case Study

This Streamlit app starts from a ChipMixer-linked coordinator-fee style address
from the paper "An Empirical Analysis of Privacy in the Lightning Network"
that was previously discussed by the user.

The goal is to find and display one transaction with strong mixer-like
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
CASE_NAME = "ChipMixer Mixer Case Study"

# Address discussed earlier as appearing in thousands of mixer transactions.
SEED_ADDRESS = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"

BACKUP_ADDRESS = "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw"

REQUEST_TIMEOUT_SECONDS = 20
SATOSHIS_PER_BTC = 100_000_000
MAX_ADDRESS_PAGES = 6

MAX_GRAPH_INPUTS = 10
MAX_GRAPH_OUTPUTS = 12

BLOCKSTREAM_URL = "https://blockstream.info"


# -----------------------------
# Page setup
# -----------------------------
# st.set_page_config(page_title=CASE_NAME, page_icon="₿", layout="wide")

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
    """Score transactions for visually strong mixer/mixer-like structure."""
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

    # Mixer-style transactions are visually stronger with many inputs and outputs.
    score += input_count * 6
    score += output_count * 8

    # Repeated output amounts are very important for a mixer-style explanation.
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


def draw_mixer_structure_graph(tx: Dict[str, Any]) -> plt.Figure:
    """Draw a simplified mixer-style transaction graph for the report.

    The old graph showed many individual inputs and outputs, which was useful
    for the app but too crowded for a paper screenshot. This version groups the
    less important nodes and highlights the main point: many inputs enter one
    transaction, then repeated output amounts appear on the output side.
    """
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    total_input_btc = sum(row["Input BTC"] for row in inputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)

    seed_inputs = [row for row in inputs if row.get("Seed Address Input")]
    seed_input_btc = sum(row["Input BTC"] for row in seed_inputs)

    # Group repeated output amounts. These are the key mixer-style signal.
    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_groups = repeated_df[repeated_df["Count"] >= 2].copy()
    repeated_groups = repeated_groups.sort_values(["Count", "Total BTC"], ascending=False)

    repeated_value_set = set(repeated_groups["Rounded Output BTC"].tolist())
    other_outputs = [
        row for row in outputs
        if round(row["Output BTC"], 8) not in repeated_value_set
    ]
    other_output_btc = sum(row["Output BTC"] for row in other_outputs)

    G = nx.DiGraph()
    tx_node = "Mixer-style\ntransaction"
    G.add_node(tx_node)

    pos = {tx_node: (0, 0)}
    labels = {tx_node: "Mixer-style\ntransaction"}
    colours = {tx_node: "#9ca3af"}
    sizes = {tx_node: 2600}

    # -----------------------------
    # Input side: keep it simple
    # -----------------------------
    input_nodes = []

    if seed_inputs:
        node = "Seed input"
        G.add_edge(node, tx_node)
        input_nodes.append(node)
        labels[node] = f"Seed input\n{seed_input_btc:.1f} BTC"
        colours[node] = "#f97316"
        sizes[node] = 2300

    other_input_count = len(inputs) - len(seed_inputs)
    other_input_btc = total_input_btc - seed_input_btc
    if other_input_count > 0:
        node = "Other inputs"
        G.add_edge(node, tx_node)
        input_nodes.append(node)
        labels[node] = f"Other inputs\n{other_input_count} addresses\n{other_input_btc:.1f} BTC"
        colours[node] = "#93c5fd"
        sizes[node] = 2500

    # If the seed was not one of the inputs, still show that this was the seed
    # address used to find the transaction, but avoid implying it funded this TX.
    if not seed_inputs:
        node = "Seed address"
        G.add_node(node)
        input_nodes.insert(0, node)
        labels[node] = "Seed address\nused to find TX"
        colours[node] = "#f97316"
        sizes[node] = 2200

    for i, node in enumerate(input_nodes):
        y = (len(input_nodes) - 1) / 2 - i
        pos[node] = (-3.2, y * 1.4)

    # -----------------------------
    # Output side: repeated groups + other outputs
    # -----------------------------
    output_nodes = []

    # Show only the strongest repeated groups so the figure stays readable.
    for index, row in repeated_groups.head(4).iterrows():
        value = float(row["Rounded Output BTC"])
        count = int(row["Count"])
        total = float(row["Total BTC"])
        node = f"Repeated {value:.8f}"
        G.add_edge(tx_node, node)
        output_nodes.append(node)
        labels[node] = f"{count} outputs\n{value:.1f} BTC each\n{total:.1f} BTC total"
        colours[node] = "#22c55e"
        sizes[node] = 2800

    remaining_repeated = repeated_groups.iloc[4:]
    remaining_repeated_count = int(remaining_repeated["Count"].sum()) if not remaining_repeated.empty else 0
    remaining_repeated_btc = float(remaining_repeated["Total BTC"].sum()) if not remaining_repeated.empty else 0.0

    grouped_other_count = len(other_outputs) + remaining_repeated_count
    grouped_other_btc = other_output_btc + remaining_repeated_btc
    if grouped_other_count > 0:
        node = "Other outputs"
        G.add_edge(tx_node, node)
        output_nodes.append(node)
        labels[node] = f"Other outputs\n{grouped_other_count} outputs\n{grouped_other_btc:.1f} BTC"
        colours[node] = "#86efac"
        sizes[node] = 2500

    for i, node in enumerate(output_nodes):
        y = (len(output_nodes) - 1) / 2 - i
        pos[node] = (3.2, y * 1.15)

    node_colours = [colours[node] for node in G.nodes()]
    node_sizes = [sizes[node] for node in G.nodes()]

    fig_height = max(5.5, 1.0 + max(len(input_nodes), len(output_nodes)) * 1.0)
    fig, ax = plt.subplots(figsize=(12, fig_height))

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
        arrowsize=18,
        width=1.6,
        alpha=0.96,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=9,
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color="#f97316", label="Seed address"),
        mpatches.Patch(color="#93c5fd", label="Grouped inputs"),
        mpatches.Patch(color="#9ca3af", label="Mixer-style transaction"),
        mpatches.Patch(color="#22c55e", label="Repeated output amount"),
        mpatches.Patch(color="#86efac", label="Other outputs"),
    ]

    ax.legend(handles=legend_handles, loc="upper right", fontsize=9)
    ax.set_title(
        "Mixer-style transaction structure: inputs are pooled and outputs are redistributed",
        pad=18,
        fontsize=13,
    )

    # Small note below the graph. This makes the screenshot clearer in the paper.
    ax.text(
        0,
        -2.8,
        f"Summary: {len(inputs)} inputs → 1 transaction → {len(outputs)} outputs. "
        f"Repeated output groups detected: {len(repeated_groups)}.",
        ha="center",
        va="center",
        fontsize=10,
        color="#374151",
    )

    ax.set_xlim(-4.4, 4.4)
    ax.set_ylim(-3.2, 3.2)
    ax.axis("off")
    fig.tight_layout()
    return fig

# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A Bitcoin tracing case study showing how mixer-style transactions weaken direct ownership tracing.")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
            This case study explores mixer behaviour using ChipMixer-style transaction patterns. Bitcoin sent into a mixer is designed to be separated from its original transaction history.
            Users could then withdraw equivalent Bitcoin to fresh addresses, making the connection between deposit and withdrawal much harder to trace.
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
            which funds. Mixer transactions are designed to disrupt that logic.
        </p>
        <p>
            When a transaction combines many inputs and creates many similar outputs, it becomes harder to map
            one input to one output. It also weakens simple tracing assumptions, because the funds may
            have been pooled and redistributed rather than moving as a simple direct payment.
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
            <strong>{len(repeated_values)} repeated output value groups</strong>, including repeated standard-sized outputs.
        </p>
        <p>
            This matters because repeated output sizes make it harder to directly match one input participant
            to one output recipient. A participant may receive value back as several smaller outputs instead of one.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Simplified mixer-style transaction graph")
st.write(
    "This simplified graph groups the inputs and outputs so the transaction is easier to read. "
    "The main point is that funds are pooled into one transaction, then redistributed into many outputs. "
    "Dark green nodes show repeated BTC amounts, which make it harder to link one input to one output."
)
st.pyplot(draw_mixer_structure_graph(selected_tx), use_container_width=True)

st.subheader("2. Selected transaction summary")
st.dataframe(build_transaction_summary(selected_tx), use_container_width=True, hide_index=True)

st.subheader("3. Repeated output value summary (key evidence)")
st.write(
    "This table is the strongest evidence in this case. It shows repeated BTC denominations across many outputs, "
    "which is consistent with redistribution in standard-sized chunks."
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
