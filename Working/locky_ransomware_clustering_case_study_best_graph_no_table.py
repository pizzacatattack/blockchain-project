"""Simple Streamlit case study for the Locky ransomware clustering example.

This version keeps the fuller spring-layout transaction graph, because that
shows the real incoming and outgoing Bitcoin flow around the seed address and
main cluster address. It removes the confusing cluster ID table and separate
cluster diagram.

Important: common-input clustering is a clue, not proof of real-world identity.
"""

import time

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


def short_hash(value, front=8, back=6):
    """Shorten a long Bitcoin address or transaction ID for tables."""
    if not isinstance(value, str) or len(value) <= front + back + 3:
        return value
    return f"{value[:front]}...{value[-back:]}"


def is_bitcoin_address(value):
    """Return True when a node looks like a Bitcoin address."""
    return str(value).startswith(("1", "3", "bc1"))


@st.cache_data(show_spinner=False)
def get_all_transactions(address):
    """Fetch all confirmed transactions for one Bitcoin address."""
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


def find_main_spend_transaction(df_inputs, df_outputs):
    """Find the transaction where the main address helped fund two outputs."""
    candidate_txs = df_inputs[
        df_inputs["Input Address"] == MAIN_CLUSTER_ADDRESS
    ]["Transaction ID"].unique()

    best = None

    for txid in candidate_txs:
        tx_inputs = df_inputs[df_inputs["Transaction ID"] == txid]
        tx_outputs = df_outputs[df_outputs["Transaction ID"] == txid]
        external_outputs = tx_outputs[tx_outputs["Output Address"] != MAIN_CLUSTER_ADDRESS]

        # Pick the clearest transaction for this case: many inputs and two outputs.
        score = (len(tx_inputs), -abs(len(external_outputs) - 2))
        if best is None or score > best["score"]:
            best = {
                "txid": txid,
                "inputs": tx_inputs,
                "outputs": external_outputs,
                "score": score,
            }

    return best


def calculate_case_numbers(seed_inputs, seed_outputs, main_inputs, main_outputs):
    """Calculate the key amounts shown at the top of the app."""
    seed_received_btc = seed_outputs[
        seed_outputs["Output Address"] == SEED_ADDRESS
    ]["Output BTC"].sum()

    seed_to_main_btc = seed_outputs[
        seed_outputs["Output Address"] == MAIN_CLUSTER_ADDRESS
    ]["Output BTC"].sum()

    main_combined_btc = main_inputs["Input BTC"].sum() if main_inputs is not None else 0

    output_values = []
    if main_outputs is not None and not main_outputs.empty:
        ordered_outputs = main_outputs.sort_values("Output Index")
        output_values = ordered_outputs["Output BTC"].tolist()

    output_1_btc = output_values[0] if len(output_values) > 0 else 0
    output_2_btc = output_values[1] if len(output_values) > 1 else 0

    return {
        "seed_received_btc": seed_received_btc,
        "seed_to_main_btc": seed_to_main_btc,
        "main_combined_btc": main_combined_btc,
        "output_1_btc": output_1_btc,
        "output_2_btc": output_2_btc,
        "output_count": len(main_outputs) if main_outputs is not None else 0,
    }


def build_full_transaction_flow_graph(df_inputs, df_outputs):
    """Build the fuller address → transaction → address flow graph.

    This uses the seed address transaction history only. That keeps the graph
    close to the original visual you liked: incoming BTC, the seed address,
    the busy central transaction and the nearby outputs.
    """
    graph = nx.DiGraph()

    # Inputs fund a transaction: input address → transaction.
    for _, row in df_inputs.iterrows():
        if pd.notna(row["Input Address"]):
            graph.add_edge(
                row["Input Address"],
                row["Transaction ID"],
                value=row["Input Value"],
                edge_type="input",
            )

    # A transaction pays outputs: transaction → output address.
    for _, row in df_outputs.iterrows():
        if pd.notna(row["Output Address"]):
            graph.add_edge(
                row["Transaction ID"],
                row["Output Address"],
                value=row["Output Value"],
                edge_type="output",
            )

    return graph


def find_main_graph_transaction(df_inputs, df_outputs):
    """Find the busy central transaction node for the graph.

    In this case-study visual, the main node is the transaction with the most
    total inputs and outputs in the seed address history. This is the hub in
    the graph, so it is coloured black.
    """
    if df_inputs.empty and df_outputs.empty:
        return None

    input_counts = df_inputs.groupby("Transaction ID").size() if not df_inputs.empty else pd.Series(dtype=int)
    output_counts = df_outputs.groupby("Transaction ID").size() if not df_outputs.empty else pd.Series(dtype=int)
    total_counts = input_counts.add(output_counts, fill_value=0)

    if total_counts.empty:
        return None

    return total_counts.sort_values(ascending=False).index[0]


def draw_full_transaction_flow_graph(graph, main_graph_transaction):
    """Draw the original-style spring graph with legend-only labels."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # This matches the original spring-style graph more closely.
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

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#000000", label="Main cluster transaction"),
        mpatches.Patch(color="#93c5fd", label="Bitcoin address"),
        mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Locky Seed Transaction Flow", pad=18)
    ax.axis("off")
    return fig


def build_story_table(numbers):
    """Create the simple story table shown in the app."""
    return pd.DataFrame([
        {
            "Step": "1. Seed address received BTC",
            "What happened": "BTC arrived at the seed address.",
            "Amount": f"{numbers['seed_received_btc']:.8f} BTC",
        },
        {
            "Step": "2. Seed sent BTC onward",
            "What happened": "The seed address sent BTC to the main cluster address.",
            "Amount": f"{numbers['seed_to_main_btc']:.8f} BTC",
        },
        {
            "Step": "3. Clustered transaction combined BTC",
            "What happened": "The main transaction combined BTC from multiple input addresses.",
            "Amount": f"{numbers['main_combined_btc']:.8f} BTC",
        },
        {
            "Step": "4. BTC went to output 1",
            "What happened": "Part of the combined BTC was sent to the first output address.",
            "Amount": f"{numbers['output_1_btc']:.8f} BTC",
        },
        {
            "Step": "5. BTC went to output 2",
            "What happened": "Part of the combined BTC was sent to the second output address.",
            "Amount": f"{numbers['output_2_btc']:.8f} BTC",
        },
    ])


def analyse_case():
    """Run the fixed Locky case study."""
    seed_txs = get_all_transactions(SEED_ADDRESS)
    main_txs = get_all_transactions(MAIN_CLUSTER_ADDRESS)

    # Use both histories for the numeric summary.
    all_txs = seed_txs + main_txs
    df_inputs = build_transaction_inputs(all_txs).drop_duplicates()
    df_outputs = build_transaction_outputs(all_txs).drop_duplicates()

    # Use seed history only for the main visual. This matches the original
    # graph style better and keeps the visual focused.
    seed_inputs = build_transaction_inputs(seed_txs)
    seed_outputs = build_transaction_outputs(seed_txs)

    main_spend = find_main_spend_transaction(df_inputs, df_outputs)

    if main_spend is None:
        main_inputs = pd.DataFrame()
        main_outputs = pd.DataFrame()
        main_txid = None
    else:
        main_inputs = main_spend["inputs"]
        main_outputs = main_spend["outputs"].copy()
        main_txid = main_spend["txid"]

    numbers = calculate_case_numbers(seed_inputs, seed_outputs, main_inputs, main_outputs)

    flow_graph = build_full_transaction_flow_graph(seed_inputs, seed_outputs)
    main_graph_transaction = find_main_graph_transaction(seed_inputs, seed_outputs)

    return {
        "df_inputs": df_inputs,
        "df_outputs": df_outputs,
        "main_inputs": main_inputs,
        "main_outputs": main_outputs,
        "main_txid": main_txid,
        "numbers": numbers,
        "flow_graph": flow_graph,
        "main_graph_transaction": main_graph_transaction,
    }


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A simple Bitcoin clustering case study using a fixed Locky-related address.")

st.markdown(
    """
    <div class="case-card">
    <h3>What this page shows</h3>
    <p>
    This page follows a fixed Bitcoin case study. It shows BTC arriving at a seed address,
    moving into a larger clustered transaction, then splitting into two output addresses.
    </p>
    <p class="small-note">
    The clustering idea is simple: when many Bitcoin addresses are used together as inputs
    in one transaction, they may be controlled by the same wallet or group. This is a clue,
    not proof of real-world identity.
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
main_outputs = results["main_outputs"]
main_inputs = results["main_inputs"]

# -----------------------------
# Top metric cards
# -----------------------------
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("BTC received by seed", f"{numbers['seed_received_btc']:.8f}")
col2.metric("Seed sent onward", f"{numbers['seed_to_main_btc']:.8f}")
col3.metric("Cluster total", f"{numbers['main_combined_btc']:.8f}")
col4.metric("Output 1", f"{numbers['output_1_btc']:.8f}")
col5.metric("Output 2", f"{numbers['output_2_btc']:.8f}")

st.markdown(
    """
    <div class="case-card">
    <h3>The visual story</h3>
    <p>
    The graph below keeps the original spring-layout view. It shows BTC moving around the seed address
    and the busy main transaction. The nodes are not labelled on purpose, so the viewer can focus on
    the pattern instead of long Bitcoin addresses.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Main graph
# -----------------------------
st.subheader("Transaction flow diagram")
st.write("Arrows show the direction BTC moved. Colours are explained in the legend.")
st.pyplot(draw_full_transaction_flow_graph(results["flow_graph"], results["main_graph_transaction"]))

# -----------------------------
# Story table
# -----------------------------
st.subheader("Story summary")
st.dataframe(build_story_table(numbers), use_container_width=True, hide_index=True)
st.info("The black node is the busy transaction where many inputs come together. This supports the clustering explanation without showing every raw address table.")

# -----------------------------
# Method notes
# -----------------------------
st.subheader("Method note")
st.markdown(
    """
    **What is clustering?**  
    Clustering means grouping Bitcoin addresses that seem related.

    **Why do we group these addresses?**  
    If many addresses are used together as inputs in one Bitcoin transaction,
    they may be controlled by the same wallet or group.

    **Important warning**  
    This does not prove who controlled the addresses. It is an investigation clue only.
    """
)
