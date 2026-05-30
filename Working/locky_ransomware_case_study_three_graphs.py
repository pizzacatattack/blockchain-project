"""Locky ransomware clustering case study Streamlit app.

This version uses three separate visuals so each graph has one clear job:

1. Payment collection: incoming payments -> Locky seed address.
2. CIOH clustering: seed address + other inputs -> shared-input transaction.
3. Flow tracing: wider transaction-flow graph around the seed address.

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


def short_value(value, front=8, back=6):
    """Shorten a long address or transaction ID for optional display."""
    if not isinstance(value, str) or len(value) <= front + back + 3:
        return value
    return f"{value[:front]}...{value[-back:]}"


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


def get_incoming_payment_txids(seed_outputs):
    """Return transaction IDs where BTC was sent to the seed address."""
    if seed_outputs.empty:
        return []

    return seed_outputs[
        seed_outputs["Output Address"] == SEED_ADDRESS
    ]["Transaction ID"].dropna().unique().tolist()


def build_payment_collection_graph(seed_inputs, seed_outputs):
    """Build graph showing incoming payment sources -> transactions -> seed."""
    graph = nx.DiGraph()
    incoming_txids = get_incoming_payment_txids(seed_outputs)

    for txid in incoming_txids:
        tx_inputs = seed_inputs[seed_inputs["Transaction ID"] == txid]

        # Add every visible input address that funded the transaction.
        for _, row in tx_inputs.iterrows():
            input_address = row["Input Address"]
            if pd.notna(input_address):
                graph.add_edge(input_address, txid)

        # Add the payment transaction into the seed address.
        graph.add_edge(txid, SEED_ADDRESS)

    return graph


def draw_payment_collection_graph(graph):
    """Draw incoming payments flowing into the seed address."""
    fig, ax = plt.subplots(figsize=(13, 7))

    if graph.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No incoming payments found", ha="center", va="center")
        ax.axis("off")
        return fig

    pos = nx.spring_layout(graph, k=0.65, seed=42)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(900)
        elif is_bitcoin_address(node):
            node_colours.append("#bfdbfe")  # light blue
            node_sizes.append(430)
        else:
            node_colours.append("#d1d5db")  # grey transaction node
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
        width=1.1,
        alpha=0.86,
    )

    legend_handles = [
        mpatches.Patch(color="#bfdbfe", label="Incoming address"),
        mpatches.Patch(color="#d1d5db", label="Payment transaction"),
        mpatches.Patch(color="#ef4444", label="Locky seed address"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Payment collection into the Locky seed address", pad=18)
    ax.axis("off")
    return fig


def find_seed_cioh_transaction(seed_inputs):
    """Find the largest multi-input transaction containing the seed address."""
    if seed_inputs.empty:
        return None

    seed_input_txs = seed_inputs[
        seed_inputs["Input Address"] == SEED_ADDRESS
    ]["Transaction ID"].dropna().unique()

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
    """Build graph showing co-spent input addresses -> shared transaction."""
    graph = nx.DiGraph()

    for _, row in cioh_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            graph.add_edge(address, cioh_txid)

    return graph


def draw_cioh_graph(graph, cioh_txid):
    """Draw the common-input ownership heuristic graph."""
    fig, ax = plt.subplots(figsize=(13, 7))

    if graph.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No shared-input transaction found", ha="center", va="center")
        ax.axis("off")
        return fig

    pos = nx.spring_layout(graph, k=0.65, seed=42)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(850)
        elif node == cioh_txid:
            node_colours.append("#000000")  # black
            node_sizes.append(760)
        else:
            node_colours.append("#93c5fd")  # blue
            node_sizes.append(430)

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
        mpatches.Patch(color="#93c5fd", label="Other co-spent address"),
        mpatches.Patch(color="#000000", label="Shared-input transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Common-input ownership heuristic (CIOH)", pad=18)
    ax.axis("off")
    return fig


def build_full_transaction_flow_graph(seed_inputs, seed_outputs):
    """Build the fuller address -> transaction -> address flow graph."""
    graph = nx.DiGraph()

    for _, row in seed_inputs.iterrows():
        if pd.notna(row["Input Address"]):
            graph.add_edge(row["Input Address"], row["Transaction ID"])

    for _, row in seed_outputs.iterrows():
        if pd.notna(row["Output Address"]):
            graph.add_edge(row["Transaction ID"], row["Output Address"])

    return graph


def draw_full_transaction_flow_graph(graph, main_graph_transaction):
    """Draw the original-style spring graph with the CIOH transaction in black."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # This keeps the original organic network look.
    pos = nx.spring_layout(graph, k=0.5, seed=42)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(760)
        elif node == main_graph_transaction:
            node_colours.append("#000000")  # black
            node_sizes.append(760)
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
        mpatches.Patch(color="#000000", label="Shared-input transaction"),
        mpatches.Patch(color="#93c5fd", label="Bitcoin address"),
        mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
        flow_arrow,
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Tracing broader Bitcoin movement", pad=18)
    ax.axis("off")
    return fig


def calculate_case_numbers(seed_inputs, seed_outputs, cioh_txid):
    """Calculate the simple numbers shown in the app."""
    incoming_txids = get_incoming_payment_txids(seed_outputs)
    seed_received_btc = seed_outputs[
        seed_outputs["Output Address"] == SEED_ADDRESS
    ]["Output BTC"].sum()

    if cioh_txid is None:
        return {
            "seed_received_btc": seed_received_btc,
            "incoming_payment_count": len(incoming_txids),
            "seed_sent_into_shared_tx_btc": 0,
            "shared_tx_total_inputs_btc": 0,
            "main_output_btc": 0,
            "secondary_output_btc": 0,
            "cioh_input_count": 0,
        }

    cioh_inputs = seed_inputs[seed_inputs["Transaction ID"] == cioh_txid].copy()
    cioh_outputs = seed_outputs[seed_outputs["Transaction ID"] == cioh_txid].copy()

    seed_sent_into_shared_tx_btc = cioh_inputs[
        cioh_inputs["Input Address"] == SEED_ADDRESS
    ]["Input BTC"].sum()

    shared_tx_total_inputs_btc = cioh_inputs["Input BTC"].sum()

    # Use largest outputs for the top cards. This is easier to read than output index order.
    output_values = cioh_outputs.sort_values("Output BTC", ascending=False)["Output BTC"].tolist()
    main_output_btc = output_values[0] if len(output_values) > 0 else 0
    secondary_output_btc = output_values[1] if len(output_values) > 1 else 0

    return {
        "seed_received_btc": seed_received_btc,
        "incoming_payment_count": len(incoming_txids),
        "seed_sent_into_shared_tx_btc": seed_sent_into_shared_tx_btc,
        "shared_tx_total_inputs_btc": shared_tx_total_inputs_btc,
        "main_output_btc": main_output_btc,
        "secondary_output_btc": secondary_output_btc,
        "cioh_input_count": cioh_inputs["Input Address"].dropna().nunique(),
    }


def build_story_table(numbers):
    """Create the short case summary table."""
    return pd.DataFrame([
        {
            "Stage": "Payment collection",
            "What happened": "BTC arrived at the Locky-linked seed address.",
            "Amount": f"{numbers['seed_received_btc']:.8f} BTC",
        },
        {
            "Stage": "Seed joins larger transaction",
            "What happened": (
                "The seed address was later used with other input addresses "
                f"in the same transaction. Total input addresses: {numbers['cioh_input_count']}."
            ),
            "Amount": f"{numbers['seed_sent_into_shared_tx_btc']:.8f} BTC from seed",
        },
        {
            "Stage": "CIOH clustering clue",
            "What happened": "Co-spending suggests the input addresses may be controlled together.",
            "Amount": f"{numbers['shared_tx_total_inputs_btc']:.8f} BTC total inputs",
        },
        {
            "Stage": "Largest output",
            "What happened": "Most of the combined BTC was sent to one output address.",
            "Amount": f"{numbers['main_output_btc']:.8f} BTC",
        },
        {
            "Stage": "Secondary output",
            "What happened": "A smaller amount was sent to another output address.",
            "Amount": f"{numbers['secondary_output_btc']:.8f} BTC",
        },
    ])


def analyse_case():
    """Run the fixed Locky case study."""
    seed_txs = get_all_transactions(SEED_ADDRESS)
    seed_inputs = build_transaction_inputs(seed_txs)
    seed_outputs = build_transaction_outputs(seed_txs)

    payment_graph = build_payment_collection_graph(seed_inputs, seed_outputs)

    cioh_txid = find_seed_cioh_transaction(seed_inputs)
    if cioh_txid is None:
        cioh_inputs = pd.DataFrame()
        cioh_graph = nx.DiGraph()
    else:
        cioh_inputs = seed_inputs[seed_inputs["Transaction ID"] == cioh_txid].copy()
        cioh_graph = build_cioh_graph(cioh_inputs, cioh_txid)

    flow_graph = build_full_transaction_flow_graph(seed_inputs, seed_outputs)
    numbers = calculate_case_numbers(seed_inputs, seed_outputs, cioh_txid)

    return {
        "seed_inputs": seed_inputs,
        "seed_outputs": seed_outputs,
        "payment_graph": payment_graph,
        "cioh_txid": cioh_txid,
        "cioh_inputs": cioh_inputs,
        "cioh_graph": cioh_graph,
        "flow_graph": flow_graph,
        "numbers": numbers,
    }


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("Collection, clustering and tracing using a fixed Locky-linked Bitcoin address.")

st.markdown(
    """
    <div class="case-card">
    <h3>Case study focus</h3>
    <p>
    This case starts with a Locky-linked Bitcoin seed address. The page shows how funds arrived,
    how the seed address was later used with other input addresses and how the surrounding Bitcoin
    movement can be traced.
    </p>
    <p class="small-note">
    Common-input clustering is an investigation clue. It does not prove real-world identity.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading the Locky case study..."):
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
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("BTC received by seed", f"{numbers['seed_received_btc']:.8f}")
col2.metric("Incoming payment txs", numbers["incoming_payment_count"])
col3.metric("CIOH input addresses", numbers["cioh_input_count"])
col4.metric("Shared tx total", f"{numbers['shared_tx_total_inputs_btc']:.8f}")
col5.metric("Largest output", f"{numbers['main_output_btc']:.8f}")
col6.metric("Secondary output", f"{numbers['secondary_output_btc']:.8f}")


# -----------------------------
# Graph 1: payment collection
# -----------------------------
st.subheader("1. Payment collection")
st.write(
    "This graph shows transactions that sent BTC into the Locky-linked seed address. "
    "It helps show why the seed address is important before looking at later movement."
)
st.pyplot(draw_payment_collection_graph(results["payment_graph"]))


# -----------------------------
# Graph 2: CIOH / clustering evidence
# -----------------------------
st.subheader("2. Common-input ownership heuristic (CIOH)")
st.write(
    f"The seed address was later used as an input with {numbers['cioh_input_count'] - 1} other address(es) "
    "in the same Bitcoin transaction. When addresses are co-spent like this, analysts may group them "
    "as likely related."
)
st.pyplot(draw_cioh_graph(results["cioh_graph"], cioh_txid))

st.info(
    "Key idea: spending from several addresses in one transaction usually requires control of those addresses. "
    "That is why this pattern can suggest shared control."
)


# -----------------------------
# Graph 3: flow tracing
# -----------------------------
st.subheader("3. Tracing broader Bitcoin movement")
st.write(
    "This graph keeps the wider transaction-flow view. The black node is the same shared-input "
    "transaction shown above, now seen in the broader movement around the seed address."
)
st.pyplot(draw_full_transaction_flow_graph(results["flow_graph"], cioh_txid))


# -----------------------------
# Summary table and method notes
# -----------------------------
st.subheader("Case summary")
st.dataframe(build_story_table(numbers), use_container_width=True, hide_index=True)

st.subheader("Method note")
st.markdown(
    """
    **Common-input ownership heuristic (CIOH)** looks for Bitcoin addresses used together
    as inputs in the same transaction.

    If several addresses are spent together, the transaction creator likely had access to
    those addresses. This can suggest shared control, so analysts may group them into a
    likely cluster.

    **Important warning:** this is not proof of who controlled the addresses. It is a clue
    that can support a wider investigation.
    """
)
