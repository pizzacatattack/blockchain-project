
"""
Locky Campaign View - Abstracted SANS-style visualisation

This is a separate exploratory Streamlit app.

It starts from one Locky-labelled address with richer activity:

    19J5etxY9rEcPkML16DMA3f9VKW4U5Su2x

The app shows:
1. inbound collection activity
2. large shared-input consolidation transactions
3. an optional transaction table with full transaction IDs

This is intentionally abstracted so the graph is readable.
It does not draw every address inside the 176-input transaction.
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
CASE_NAME = "Locky Campaign View"
COLLECTOR_ADDRESS = "19J5etxY9rEcPkML16DMA3f9VKW4U5Su2x"

REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.15
SATOSHIS = 100_000_000


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
        width: 72px;
        height: 72px;
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
# Helper functions
# -----------------------------
def sats_to_btc(value):
    """Convert satoshis to BTC."""
    if value is None:
        return 0.0
    return value / SATOSHIS


def format_btc(value):
    """Format BTC neatly."""
    return f"{value:,.8f} BTC"


def short_txid(txid):
    """Shorten txid for graph labels only."""
    return f"{txid[:8]}...{txid[-6:]}"


@st.cache_data(show_spinner=False)
def fetch_address_transactions(address):
    """Fetch confirmed transactions for one Bitcoin address from Blockstream."""
    url = f"https://blockstream.info/api/address/{address}/txs"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(API_SLEEP_SECONDS)
    return response.json()


@st.cache_data(show_spinner=False)
def fetch_transaction(txid):
    """Fetch one transaction from Blockstream."""
    url = f"https://blockstream.info/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(API_SLEEP_SECONDS)
    return response.json()


def analyse_transactions(txs, address):
    """Create a simple summary table for transactions involving the address."""
    rows = []

    for tx in txs:
        txid = tx["txid"]
        inputs = tx.get("vin", [])
        outputs = tx.get("vout", [])

        received = 0.0
        spent = 0.0
        total_input = 0.0
        total_output = 0.0

        for vin in inputs:
            prevout = vin.get("prevout") or {}
            value = sats_to_btc(prevout.get("value", 0))
            total_input += value

            if prevout.get("scriptpubkey_address") == address:
                spent += value

        for vout in outputs:
            value = sats_to_btc(vout.get("value", 0))
            total_output += value

            if vout.get("scriptpubkey_address") == address:
                received += value

        if received > 0 and spent == 0:
            direction = "Received"
        elif spent > 0 and received == 0:
            direction = "Spent"
        elif received > 0 and spent > 0:
            direction = "Both"
        else:
            direction = "Related"

        rows.append(
            {
                "Transaction ID": txid,
                "Direction": direction,
                "BTC received by collector": received,
                "BTC spent by collector": spent,
                "Input count": len(inputs),
                "Output count": len(outputs),
                "Total input BTC": total_input,
                "Total output BTC": total_output,
            }
        )

    df = pd.DataFrame(rows)

    # Keep display order stable: larger consolidations first for spent, larger receives first for received.
    return df


def build_inbound_graph(summary_df, collector_address):
    """Build a readable graph of incoming payments into the collector address."""
    G = nx.DiGraph()

    collector_node = collector_address
    G.add_node(
        collector_node,
        kind="collector",
        label=f"Locky-labelled address\n{collector_address}",
        size=2600,
    )

    inbound = summary_df[summary_df["BTC received by collector"] > 0].copy()
    inbound = inbound.sort_values("BTC received by collector", ascending=False)

    for idx, row in inbound.iterrows():
        amount = row["BTC received by collector"]
        txid = row["Transaction ID"]

        source_node = f"incoming_source_{idx}"
        tx_node = f"incoming_tx_{idx}"

        G.add_node(
            source_node,
            kind="source",
            label=f"Incoming source\n{format_btc(amount)}",
            size=950,
        )

        G.add_node(
            tx_node,
            kind="transaction",
            label=f"Incoming transaction\n{short_txid(txid)}",
            size=900,
        )

        G.add_edge(source_node, tx_node)
        G.add_edge(tx_node, collector_node)

    return G


def build_consolidation_graph(summary_df, collector_address):
    """Build an abstract graph of the large shared-input transactions."""
    G = nx.DiGraph()

    collector_node = collector_address
    G.add_node(
        collector_node,
        kind="collector",
        label=f"Locky-labelled address\n{collector_address}",
        size=2800,
    )

    spent = summary_df[summary_df["BTC spent by collector"] > 0].copy()
    spent = spent.sort_values("Input count", ascending=False)

    for idx, row in spent.iterrows():
        txid = row["Transaction ID"]
        input_count = int(row["Input count"])
        output_count = int(row["Output count"])
        collector_spent = row["BTC spent by collector"]
        total_input = row["Total input BTC"]
        co_input_count = max(input_count - 1, 0)

        co_input_node = f"co_inputs_{idx}"
        tx_node = f"shared_tx_{idx}"
        output_node = f"outputs_{idx}"

        # Size scales gently with the number of co-inputs.
        co_size = max(900, min(3600, 600 + co_input_count * 18))

        G.add_node(
            co_input_node,
            kind="co_inputs",
            label=f"{co_input_count} other co-spent inputs\nTransaction total: {format_btc(total_input)}",
            size=co_size,
        )

        G.add_node(
            tx_node,
            kind="transaction",
            label=f"Shared-input transaction\n{input_count} inputs / {output_count} outputs\n{short_txid(txid)}",
            size=1600,
        )

        G.add_node(
            output_node,
            kind="output",
            label=f"{output_count} outputs\nfrom shared transaction",
            size=1100,
        )

        G.add_edge(collector_node, tx_node)
        G.add_edge(co_input_node, tx_node)
        G.add_edge(tx_node, output_node)

    return G


def draw_graph(G, title, figsize=(13, 7), seed=42):
    """Draw a readable network graph."""
    fig, ax = plt.subplots(figsize=figsize)

    pos = nx.spring_layout(G, seed=seed, k=1.25, iterations=140)

    node_colors = []
    node_sizes = []

    for node, data in G.nodes(data=True):
        kind = data.get("kind")

        if kind == "collector":
            node_colors.append("#d62728")  # red
        elif kind == "source":
            node_colors.append("#9ecae1")  # light blue
        elif kind == "co_inputs":
            node_colors.append("#1f77b4")  # blue
        elif kind == "transaction":
            node_colors.append("#111111")  # black
        elif kind == "output":
            node_colors.append("#74c476")  # green
        else:
            node_colors.append("#cccccc")

        node_sizes.append(data.get("size", 900))

    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
        width=1.35,
        edge_color="#555555",
        alpha=0.45,
        connectionstyle="arc3,rad=0.08",
    )

    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        linewidths=1.0,
        edgecolors="white",
    )

    labels = {node: data.get("label", node) for node, data in G.nodes(data=True)}

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8,
        font_color="#111111",
        ax=ax,
    )

    legend_items = [
        mpatches.Patch(color="#d62728", label="Locky-labelled address"),
        mpatches.Patch(color="#9ecae1", label="Incoming source"),
        mpatches.Patch(color="#1f77b4", label="Grouped co-spent inputs"),
        mpatches.Patch(color="#111111", label="Bitcoin transaction"),
        mpatches.Patch(color="#74c476", label="Outputs"),
    ]

    ax.legend(handles=legend_items, loc="upper left", frameon=True)
    ax.set_title(title, fontsize=15, pad=12)
    ax.axis("off")
    plt.tight_layout()

    return fig


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("Exploratory campaign-scale view using one busier Locky-labelled address.")

st.markdown(
    f"""
    <div class="case-card">
    <h3>Case focus</h3>
    <p>
    This page starts from the Locky-labelled address below and looks at its collection
    and consolidation behaviour.
    </p>
    <p><b>{COLLECTOR_ADDRESS}</b></p>
    <p class="small-note">
    This is an exploratory campaign view. It is useful for spotting patterns, but it should
    not be treated as proof of real-world identity.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Fetching transactions from Blockstream..."):
        txs = fetch_address_transactions(COLLECTOR_ADDRESS)
        summary_df = analyse_transactions(txs, COLLECTOR_ADDRESS)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch blockchain data from Blockstream: {exc}")
    st.stop()

received_df = summary_df[summary_df["BTC received by collector"] > 0].copy()
spent_df = summary_df[summary_df["BTC spent by collector"] > 0].copy()

total_received = received_df["BTC received by collector"].sum()
total_spent = spent_df["BTC spent by collector"].sum()
largest_shared_input = int(spent_df["Input count"].max()) if not spent_df.empty else 0
spent_count = len(spent_df)
received_count = len(received_df)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Transactions fetched", len(summary_df))
col2.metric("Inbound transactions", received_count)
col3.metric("Outbound spends", spent_count)
col4.metric("Largest shared spend", f"{largest_shared_input} inputs")
col5.metric("Total received", format_btc(total_received))

st.markdown(
    """
    <div class="case-card">
    <h3>Why this is interesting</h3>
    <p>
    This address received several smaller amounts, then later appeared in much larger
    shared-input transactions. That pattern is useful for campaign mapping because it can
    show how funds move from smaller collection activity into larger consolidation events.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Graph 1: inbound collection
# -----------------------------
st.subheader("1. Inbound collection view")
st.write(
    "This graph shows the transactions where the Locky-labelled address received BTC. "
    "It is a collection view, not a proof that every source is Locky-controlled."
)

inbound_graph = build_inbound_graph(summary_df, COLLECTOR_ADDRESS)
st.pyplot(draw_graph(inbound_graph, "Inbound collection into Locky-labelled address", seed=7))

# -----------------------------
# Graph 2: consolidation
# -----------------------------
st.subheader("2. Shared-input consolidation view")
st.write(
    "This graph shows where the address was spent together with many other inputs. "
    "These large shared-input transactions are the more important campaign-style pattern."
)

consolidation_graph = build_consolidation_graph(summary_df, COLLECTOR_ADDRESS)
st.pyplot(draw_graph(consolidation_graph, "Large shared-input consolidation transactions", seed=12))

# -----------------------------
# Tables
# -----------------------------
st.subheader("Transaction summary")

display_df = summary_df.copy()
display_df["BTC received by collector"] = display_df["BTC received by collector"].map(lambda x: f"{x:.8f}")
display_df["BTC spent by collector"] = display_df["BTC spent by collector"].map(lambda x: f"{x:.8f}")
display_df["Total input BTC"] = display_df["Total input BTC"].map(lambda x: f"{x:.8f}")
display_df["Total output BTC"] = display_df["Total output BTC"].map(lambda x: f"{x:.8f}")

st.dataframe(display_df, use_container_width=True)

st.markdown(
    """
    <div class="case-card">
    <h3>Interpretation note</h3>
    <p>
    The inbound graph shows funds arriving at the address. The consolidation graph is where
    the common-input idea becomes more relevant: the address is spent alongside many other
    inputs in the same transaction.
    </p>
    <p>
    This supports a campaign-mapping view, but it still remains heuristic analysis.
    Collaborative transactions, exchanges, services and wallet behaviour can complicate
    ownership assumptions.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)
