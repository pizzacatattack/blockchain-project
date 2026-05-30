"""Locky ransomware clustering case study Streamlit app.

This version separates the two ideas that were getting mixed together:

1. CIOH graph: shows the common-input ownership heuristic.
   This is the clustering evidence.

2. Flow graph: shows the broader Bitcoin movement around the seed address.
   This is the tracing / story visual.

The app keeps the address fixed so it works as a clean case-study display.
Important: clustering is a clue, not proof of real-world identity.
"""

import time

import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed case settings
# -----------------------------
CASE_NAME = "Locky Ransomware Clustering Case Study"
SEED_ADDRESS = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"

# This is kept as a known address from the earlier version of the case study.
# The app does not let the user edit it from the sidebar.
MAIN_CLUSTER_ADDRESS = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"

REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.2


# -----------------------------
# Page setup
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
        width: 86px;
        height: 86px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 48px;
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
# Helper functions
# -----------------------------
def sats_to_btc(value):
    """Convert satoshis to BTC."""
    return value / 100_000_000 if value is not None else 0


def is_bitcoin_address(value):
    """Return True when a node looks like a Bitcoin address."""
    return str(value).startswith(("1", "3", "bc1"))


@st.cache_data(show_spinner=False)
def get_all_transactions(address):
    """Fetch all confirmed transactions for one Bitcoin address from Blockstream."""
    all_txs = []
    last_seen = None

    while True:
        if last_seen:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain"

        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        all_txs.extend(data)

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(API_SLEEP_SECONDS)

    return all_txs


def build_transaction_inputs(all_txs):
    """Create one row for every input in every transaction."""
    rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vin in enumerate(tx.get("vin", [])):
            prevout = vin.get("prevout", {}) or {}
            rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Input Index": i,
                "Input Address": prevout.get("scriptpubkey_address"),
                "Input Value": prevout.get("value", 0),
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="s", errors="coerce")
        df["Input BTC"] = df["Input Value"].apply(sats_to_btc)

    return df


def build_transaction_outputs(all_txs):
    """Create one row for every output in every transaction."""
    rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vout in enumerate(tx.get("vout", [])):
            rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Output Index": i,
                "Output Address": vout.get("scriptpubkey_address"),
                "Output Value": vout.get("value", 0),
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="s", errors="coerce")
        df["Output BTC"] = df["Output Value"].apply(sats_to_btc)

    return df


def find_seed_cioh_transaction(seed_inputs):
    """Find the important multi-input transaction containing the seed address.

    CIOH means common-input ownership heuristic. For this case study we want the
    transaction where the seed address appears as an input with many other input
    addresses. That is the clean clustering example.
    """
    if seed_inputs.empty:
        return None

    # Keep only transactions where the seed address is one of the inputs.
    seed_input_txs = seed_inputs[
        seed_inputs["Input Address"] == SEED_ADDRESS
    ]["Transaction ID"].unique()

    if len(seed_input_txs) == 0:
        return None

    best_txid = None
    best_unique_input_count = 0

    for txid in seed_input_txs:
        tx_inputs = seed_inputs[seed_inputs["Transaction ID"] == txid]
        unique_input_count = tx_inputs["Input Address"].dropna().nunique()

        if unique_input_count > best_unique_input_count:
            best_unique_input_count = unique_input_count
            best_txid = txid

    return best_txid


def build_cioh_graph(cioh_inputs, cioh_txid):
    """Build the small CIOH graph: input addresses -> shared transaction."""
    graph = nx.DiGraph()

    for _, row in cioh_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            graph.add_edge(address, cioh_txid)

    return graph


def draw_cioh_graph(graph, cioh_txid):
    """Draw the CIOH graph.

    This graph intentionally shows only the shared-input transaction. It is not
    trying to show every later movement of funds.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    # Spring layout keeps it compact and readable.
    pos = nx.spring_layout(graph, k=0.7, seed=42)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(820)
        elif node == cioh_txid:
            node_colours.append("#000000")  # black
            node_sizes.append(700)
        else:
            node_colours.append("#93c5fd")  # blue
            node_sizes.append(420)

    nx.draw(
        graph,
        pos,
        ax=ax,
        with_labels=False,
        node_size=node_sizes,
        node_color=node_colours,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=14,
        width=1.2,
        alpha=0.88,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Locky seed address"),
        mpatches.Patch(color="#93c5fd", label="Other input address"),
        mpatches.Patch(color="#000000", label="Shared-input transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Graph 1: CIOH clustering example", pad=18)
    ax.axis("off")
    return fig


def build_full_transaction_flow_graph(seed_inputs, seed_outputs):
    """Build the fuller address -> transaction -> address flow graph.

    This is the eye-catching graph that shows the wider flow around the seed.
    """
    graph = nx.DiGraph()

    for _, row in seed_inputs.iterrows():
        if pd.notna(row["Input Address"]):
            graph.add_edge(row["Input Address"], row["Transaction ID"])

    for _, row in seed_outputs.iterrows():
        if pd.notna(row["Output Address"]):
            graph.add_edge(row["Transaction ID"], row["Output Address"])

    return graph


def draw_full_transaction_flow_graph(graph, main_graph_transaction):
    """Draw the original-style spring graph with the main node in black."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # This matches the original graph style the user preferred.
    pos = nx.spring_layout(graph, k=0.5, seed=42)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(760)
        elif node == main_graph_transaction:
            node_colours.append("#000000")  # black
            node_sizes.append(720)
        elif is_bitcoin_address(node):
            node_colours.append("#93c5fd")  # blue
            node_sizes.append(420)
        else:
            node_colours.append("#d1d5db")  # grey
            node_sizes.append(260)

    nx.draw(
        graph,
        pos,
        ax=ax,
        with_labels=False,
        node_size=node_sizes,
        node_color=node_colours,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=14,
        width=1.2,
        alpha=0.85,
    )

    flow_arrow = mlines.Line2D(
        [], [],
        color="#333333",
        marker=">",
        linestyle="-",
        markersize=7,
        label="BTC flow direction",
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#000000", label="Main shared-input transaction"),
        mpatches.Patch(color="#93c5fd", label="Bitcoin address"),
        mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
        flow_arrow,
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Graph 2: Bitcoin flow around the Locky seed address", pad=18)
    ax.axis("off")
    return fig


def calculate_case_numbers(seed_inputs, seed_outputs, cioh_txid):
    """Calculate the simple amounts shown in the app."""
    if cioh_txid is None:
        return {
            "seed_received_btc": 0,
            "seed_sent_into_shared_tx_btc": 0,
            "shared_tx_total_inputs_btc": 0,
            "output_1_btc": 0,
            "output_2_btc": 0,
            "cioh_input_count": 0,
        }

    cioh_inputs = seed_inputs[seed_inputs["Transaction ID"] == cioh_txid].copy()
    cioh_outputs = seed_outputs[seed_outputs["Transaction ID"] == cioh_txid].copy()

    seed_received_btc = seed_outputs[
        seed_outputs["Output Address"] == SEED_ADDRESS
    ]["Output BTC"].sum()

    seed_sent_into_shared_tx_btc = cioh_inputs[
        cioh_inputs["Input Address"] == SEED_ADDRESS
    ]["Input BTC"].sum()

    shared_tx_total_inputs_btc = cioh_inputs["Input BTC"].sum()

    ordered_outputs = cioh_outputs.sort_values("Output Index")
    output_values = ordered_outputs["Output BTC"].tolist()
    output_1_btc = output_values[0] if len(output_values) > 0 else 0
    output_2_btc = output_values[1] if len(output_values) > 1 else 0

    return {
        "seed_received_btc": seed_received_btc,
        "seed_sent_into_shared_tx_btc": seed_sent_into_shared_tx_btc,
        "shared_tx_total_inputs_btc": shared_tx_total_inputs_btc,
        "output_1_btc": output_1_btc,
        "output_2_btc": output_2_btc,
        "cioh_input_count": cioh_inputs["Input Address"].dropna().nunique(),
    }


def build_story_table(numbers):
    """Create the simple story table."""
    return pd.DataFrame([
        {
            "Step": "1. Seed address received BTC",
            "What happened": "BTC arrived at the Locky-linked seed address.",
            "Amount": f"{numbers['seed_received_btc']:.8f} BTC",
        },
        {
            "Step": "2. Seed appeared in a shared-input transaction",
            "What happened": f"The seed was used together with other addresses as inputs. Total input addresses: {numbers['cioh_input_count']}.",
            "Amount": f"{numbers['seed_sent_into_shared_tx_btc']:.8f} BTC from seed",
        },
        {
            "Step": "3. CIOH suggests likely shared control",
            "What happened": "Because the addresses were co-spent, they may be controlled by the same wallet or group.",
            "Amount": f"{numbers['shared_tx_total_inputs_btc']:.8f} BTC total inputs",
        },
        {
            "Step": "4. BTC was split to output 1",
            "What happened": "Part of the combined BTC was sent to the first output address.",
            "Amount": f"{numbers['output_1_btc']:.8f} BTC",
        },
        {
            "Step": "5. BTC was split to output 2",
            "What happened": "Part of the combined BTC was sent to the second output address.",
            "Amount": f"{numbers['output_2_btc']:.8f} BTC",
        },
    ])


def analyse_case():
    """Run the fixed Locky case study."""
    seed_txs = get_all_transactions(SEED_ADDRESS)
    seed_inputs = build_transaction_inputs(seed_txs)
    seed_outputs = build_transaction_outputs(seed_txs)

    cioh_txid = find_seed_cioh_transaction(seed_inputs)

    if cioh_txid is None:
        cioh_inputs = pd.DataFrame()
        cioh_graph = nx.DiGraph()
    else:
        cioh_inputs = seed_inputs[seed_inputs["Transaction ID"] == cioh_txid].copy()
        cioh_graph = build_cioh_graph(cioh_inputs, cioh_txid)

    flow_graph = build_full_transaction_flow_graph(seed_inputs, seed_outputs)

    # Use the same transaction for the black node in the flow graph. This connects
    # Graph 1 and Graph 2 cleanly: the shared-input transaction is the visual hub.
    main_graph_transaction = cioh_txid

    numbers = calculate_case_numbers(seed_inputs, seed_outputs, cioh_txid)

    return {
        "seed_inputs": seed_inputs,
        "seed_outputs": seed_outputs,
        "cioh_txid": cioh_txid,
        "cioh_inputs": cioh_inputs,
        "cioh_graph": cioh_graph,
        "flow_graph": flow_graph,
        "main_graph_transaction": main_graph_transaction,
        "numbers": numbers,
    }


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A fixed Locky case study showing clustering first, then flow tracing.")

st.markdown(
    """
    <div class="case-card">
    <h3>What this page shows</h3>
    <p>
    This page separates two ideas. First, it shows why a group of addresses may be related
    using the common-input ownership heuristic. Then it shows the wider Bitcoin flow around
    the Locky-linked seed address.
    </p>
    <p class="small-note">
    This is an investigation clue, not proof of real-world identity.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading the fixed Locky case study..."):
        results = analyse_case()
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch Bitcoin data from Blockstream: {exc}")
    st.stop()

numbers = results["numbers"]
cioh_txid = results["cioh_txid"]

if cioh_txid is None:
    st.error("Could not find a multi-input transaction involving the seed address.")
    st.stop()


# -----------------------------
# Top metric cards
# -----------------------------
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("BTC received by seed", f"{numbers['seed_received_btc']:.8f}")
col2.metric("Seed input in shared tx", f"{numbers['seed_sent_into_shared_tx_btc']:.8f}")
col3.metric("Shared transaction total", f"{numbers['shared_tx_total_inputs_btc']:.8f}")
col4.metric("Output 1", f"{numbers['output_1_btc']:.8f}")
col5.metric("Output 2", f"{numbers['output_2_btc']:.8f}")


# -----------------------------
# Graph 1: CIOH / clustering evidence
# -----------------------------
st.subheader("Graph 1: why clustering is inferred")
st.write(
    f"The seed address was used as an input with {numbers['cioh_input_count'] - 1} other address(es) "
    "in the same Bitcoin transaction. This is the common-input ownership heuristic."
)
st.pyplot(draw_cioh_graph(results["cioh_graph"], cioh_txid))

st.info(
    "Plain English: if many addresses are used together to fund one transaction, "
    "the same wallet or group may control them. This is called address clustering."
)


# -----------------------------
# Graph 2: flow tracing
# -----------------------------
st.subheader("Graph 2: where the BTC moved")
st.write(
    "This graph uses the same shared-input transaction as the black node, but shows the wider flow "
    "around the seed address. Arrows show BTC movement."
)
st.pyplot(draw_full_transaction_flow_graph(results["flow_graph"], results["main_graph_transaction"]))


# -----------------------------
# Story table
# -----------------------------
st.subheader("Story summary")
st.dataframe(build_story_table(numbers), use_container_width=True, hide_index=True)


# -----------------------------
# Method notes
# -----------------------------
st.subheader("Method note")
st.markdown(
    """
    **Common-input ownership heuristic (CIOH)** means looking for Bitcoin addresses
    that were used together as inputs in the same transaction.

    If several addresses are spent together, the transaction creator likely had access
    to those addresses. This can suggest shared control, so analysts group those
    addresses into a likely cluster.

    **Important warning:** this does not prove who controlled the addresses. It is only
    a clue that can support a wider investigation.
    """
)
