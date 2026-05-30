"""
Locky Ransomware Clustering Case Study

This Streamlit app demonstrates the common-input ownership heuristic (CIOH)
using a Locky-labelled Bitcoin consolidation transaction.

The app is intentionally hardcoded for this case study so the display stays
clear and consistent for assessment/demo purposes.
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
CIOH_TXID = "275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"
REQUEST_TIMEOUT_SECONDS = 20


# These are the 30 input addresses in the CIOH transaction.
# In the Ransomwhere dataset checked by the user, all 30 are labelled as Locky.
LOCKY_INPUT_ADDRESSES = [
    "1dzRo5aJ9n5Et6iGNkdyu4w1gguDp7cXm",
    "1GdyEzVchXj4EKr1FMbu9mKpsAN64NvksY",
    "1EbUEdu6p6o68Qd6CeFBSZ94woifR7R7eT",
    "178HGmCfR26dSSiFxJQah1U588p2CjgX7f",
    "12WMZBt1boPV5sMKknDeYSe8EximnGuV41",
    "1DrGzqusugQZkA8RuB1556v11jo6TcwLum",
    "1Jb7zNP86WHNhJTFdWsX9mKu3akN691cgU",
    "1R9gMbvM2FnRmG1U9HJT1dupdK32kdfyd",
    "1PWxRF5EpAuP88Dpu6fYPfv5rmaYPqpB7i",
    "1Ba6mozmB7beR6GoFgWFWfK9FeQdSN8gVi",
    "1DjshGrDYVo87Ja4DxpfCof3FpUZsDQpZM",
    "1HcViPc1eTSVN4d8QWDCQXU3hG51dfUGXs",
    "1NAVhUixJ2HjRJXk8j96tA7kp3u6oRi9Zb",
    "1FRDJam9RYgn8W6zdQK3Ge7zrWwmf4vvsB",
    "1DiMM75HqhsJDfnLGyRJMfNMDPvgkZ4t6p",
    "17iuC3ca7RKnCuh7HJ1zUXfg4SsLU2suCr",
    "1BogoPcqRv8vvefr2P4zK81nBxw5urw5Zp",
    "16Akt4JeRRKySzKDBRJEEweBJ8JRpUp5dE",
    "16iTUac8jkf4LPud1SZBGJiyKWcoFNPA6T",
    "12nkRSvz5g77z5tnHrjNmkmgmqG8Gdv1x6",
    "1TvGxNJSk7rRZf7p1bb7hHs2ZDiJLiHLG",
    "1KhYxWq9r9EVkiLnLqd1wPACi6xeCaNf8C",
    "18zV1WGWCbqb632n4dPXWjUJTHymxFc15Z",
    "1NzED3mXPyAk4VwXZHxrVp9aGE2Tcgq7hQ",
    "18B5hQ2DuxGzTCxNaXL2J3AsWX3FPPeMup",
    "1A4dMpfqgTTNSWUKier3t9aMajHr57yc7W",
    "1QBGqWgFRrFLvzxx3kojQYUczuEbUne6Xd",
    "1px2pnCAfc1si5Zs8Dj5y5wqQ7otiNcyL",
    "15H9WE7ADd1mZjYPGjAj1jdFjJwt7qFt6F",
    "1LegLVX1MM4UPoP4qxkrtcwnFpJk4pHYBH",
]


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


# -----------------------------
# Helper functions
# -----------------------------
def sats_to_btc(value):
    """Convert satoshis to BTC."""
    if value is None:
        return 0
    return value / 100_000_000


def short_hash(value, front=8, back=6):
    """Shorten a long Bitcoin address or transaction ID for tables."""
    if not isinstance(value, str) or len(value) <= front + back + 3:
        return value
    return f"{value[:front]}...{value[-back:]}"


def is_bitcoin_address(value):
    """Return True when a graph node looks like a Bitcoin address."""
    return str(value).startswith(("1", "3", "bc1"))


@st.cache_data(show_spinner=False)
def get_transaction(txid):
    """Fetch one confirmed transaction from Blockstream."""
    url = f"https://blockstream.info/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def build_input_output_tables(tx):
    """Build simple input and output dataframes for one transaction."""
    input_rows = []
    output_rows = []

    txid = tx["txid"]

    for i, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        input_rows.append(
            {
                "Transaction ID": txid,
                "Input Index": i,
                "Input Address": prevout.get("scriptpubkey_address"),
                "Input Value": prevout.get("value", 0),
                "Input BTC": sats_to_btc(prevout.get("value", 0)),
            }
        )

    for i, vout in enumerate(tx.get("vout", [])):
        output_rows.append(
            {
                "Transaction ID": txid,
                "Output Index": i,
                "Output Address": vout.get("scriptpubkey_address"),
                "Output Value": vout.get("value", 0),
                "Output BTC": sats_to_btc(vout.get("value", 0)),
            }
        )

    return pd.DataFrame(input_rows), pd.DataFrame(output_rows)


def calculate_case_numbers(df_inputs, df_outputs):
    """Calculate the core numbers shown in the app."""
    seed_contribution = df_inputs.loc[
        df_inputs["Input Address"] == SEED_ADDRESS, "Input BTC"
    ].sum()

    total_input_btc = df_inputs["Input BTC"].sum()

    sorted_outputs = df_outputs.sort_values("Output BTC", ascending=False).reset_index(drop=True)
    main_output_btc = sorted_outputs.loc[0, "Output BTC"] if len(sorted_outputs) > 0 else 0
    second_output_btc = sorted_outputs.loc[1, "Output BTC"] if len(sorted_outputs) > 1 else 0

    return {
        "input_count": df_inputs["Input Address"].nunique(),
        "seed_contribution": seed_contribution,
        "total_input_btc": total_input_btc,
        "output_count": len(df_outputs),
        "main_output_btc": main_output_btc,
        "second_output_btc": second_output_btc,
    }


def build_cioh_graph(df_inputs, df_outputs):
    """Build the academic CIOH graph: 30 Locky inputs -> shared transaction -> outputs."""
    G = nx.DiGraph()
    shared_tx_node = "Shared transaction"

    for _, row in df_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            G.add_edge(address, shared_tx_node, value=row["Input BTC"])

    for _, row in df_outputs.iterrows():
        address = row["Output Address"]
        if pd.notna(address):
            G.add_edge(shared_tx_node, address, value=row["Output BTC"])

    return G, shared_tx_node


def draw_cioh_graph(G, shared_tx_node):
    """Draw a clear CIOH graph without node labels."""
    fig, ax = plt.subplots(figsize=(13, 7))

    # A fixed layout makes this graph easier to read:
    # inputs around the left/centre, transaction in the middle, outputs on the right.
    input_nodes = [n for n in G.nodes() if n in LOCKY_INPUT_ADDRESSES]
    output_nodes = [n for n in G.nodes() if n not in input_nodes and n != shared_tx_node]

    pos = {}

    # Place input addresses in a circle on the left.
    input_layout = nx.circular_layout(input_nodes, scale=2.8, center=(-1.8, 0))
    pos.update(input_layout)

    # Place the shared transaction in the middle.
    pos[shared_tx_node] = (1.3, 0)

    # Place outputs on the right.
    if len(output_nodes) == 1:
        pos[output_nodes[0]] = (4.1, 0)
    else:
        for i, node in enumerate(output_nodes):
            y = 0.7 if i == 0 else -0.7
            pos[node] = (4.1, y)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")  # red
            node_sizes.append(780)
        elif node == shared_tx_node:
            node_colours.append("#111827")  # black
            node_sizes.append(950)
        elif node in LOCKY_INPUT_ADDRESSES:
            node_colours.append("#93c5fd")  # blue
            node_sizes.append(480)
        else:
            node_colours.append("#22c55e")  # green outputs
            node_sizes.append(650)

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_size=node_sizes,
        node_color=node_colours,
        edge_color="#6b7280",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=14,
        width=1.4,
        alpha=0.9,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#93c5fd", label="Other Locky-labelled input address"),
        mpatches.Patch(color="#111827", label="Shared Bitcoin transaction"),
        mpatches.Patch(color="#22c55e", label="Output address"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Common-input ownership heuristic: 30 Locky-labelled inputs spent together", pad=18)
    ax.axis("off")
    return fig


def build_favourite_flow_graph(df_inputs, df_outputs):
    """Build the dramatic consolidation graph from the same CIOH transaction."""
    G = nx.DiGraph()
    tx_node = CIOH_TXID

    for _, row in df_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            G.add_edge(address, tx_node, value=row["Input BTC"], edge_type="input")

    for _, row in df_outputs.iterrows():
        address = row["Output Address"]
        if pd.notna(address):
            G.add_edge(tx_node, address, value=row["Output BTC"], edge_type="output")

    return G


def draw_favourite_flow_graph(G):
    """Draw the visually striking spring graph, with the main transaction in black."""
    fig, ax = plt.subplots(figsize=(13, 7))

    pos = nx.spring_layout(G, k=0.75, seed=42)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")
            node_sizes.append(850)
        elif node == CIOH_TXID:
            node_colours.append("#111827")
            node_sizes.append(950)
        elif is_bitcoin_address(node):
            # Outputs and inputs are both addresses. This graph is for dramatic flow,
            # so we keep them blue to avoid overcomplicating the visual.
            node_colours.append("#93c5fd")
            node_sizes.append(540)
        else:
            node_colours.append("#d1d5db")
            node_sizes.append(420)

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_size=node_sizes,
        node_color=node_colours,
        edge_color="#6b7280",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=15,
        width=1.6,
        alpha=0.9,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#93c5fd", label="Bitcoin address"),
        mpatches.Patch(color="#111827", label="Main consolidation transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Locky BTC consolidation flow", pad=18)
    ax.axis("off")
    return fig


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A fixed case study showing Bitcoin address clustering with the common-input ownership heuristic.")

st.markdown(
    """
    <div class="case-card">
    <h3>Case focus</h3>
    <p>
    This case starts with a Locky-labelled Bitcoin address and examines one transaction where it was spent
    together with other Locky-labelled addresses. The purpose is to show how the common-input ownership
    heuristic can support address clustering.
    </p>
    <p class="small-note">
    This is heuristic analysis. It suggests likely shared control, but it does not prove real-world identity.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading Locky transaction data from Blockstream..."):
        cioh_tx = get_transaction(CIOH_TXID)
        df_inputs, df_outputs = build_input_output_tables(cioh_tx)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch Bitcoin data from Blockstream: {exc}")
    st.stop()

numbers = calculate_case_numbers(df_inputs, df_outputs)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Locky-labelled inputs", numbers["input_count"])
col2.metric("Seed contribution", f"{numbers['seed_contribution']:.4f} BTC")
col3.metric("BTC combined", f"{numbers['total_input_btc']:.4f} BTC")
col4.metric("Main output", f"{numbers['main_output_btc']:.4f} BTC")
col5.metric("Second output", f"{numbers['second_output_btc']:.8f} BTC")

st.markdown(
    """
    <div class="case-card">
    <h3>What the transaction shows</h3>
    <p>
    Thirty Locky-labelled addresses were used together as inputs in one Bitcoin transaction.
    Under the common-input ownership heuristic, this supports the idea that the input addresses
    may have been controlled by the same wallet or operator group.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Common-input ownership heuristic evidence")
st.write(
    "This graph shows the key clustering evidence: the seed address and the other Locky-labelled input addresses were spent together in the same transaction."
)
cioh_graph, shared_tx_node = build_cioh_graph(df_inputs, df_outputs)
st.pyplot(draw_cioh_graph(cioh_graph, shared_tx_node))

st.subheader("2. Consolidation flow")
st.write(
    "This graph shows the same transaction as a flow diagram. Many Locky-labelled inputs are consolidated, then almost all BTC is sent to one output address."
)
flow_graph = build_favourite_flow_graph(df_inputs, df_outputs)
st.pyplot(draw_favourite_flow_graph(flow_graph))

st.subheader("Transaction summary")
summary_rows = [
    {
        "Step": "1. Starting point",
        "What happened": "The seed address is one of 30 Locky-labelled inputs in the transaction.",
        "BTC": f"{numbers['seed_contribution']:.4f} BTC from the seed",
    },
    {
        "Step": "2. CIOH evidence",
        "What happened": "The 30 input addresses were spent together in one transaction.",
        "BTC": f"{numbers['total_input_btc']:.4f} BTC combined",
    },
    {
        "Step": "3. Main output",
        "What happened": "Most of the combined BTC was sent to one output address.",
        "BTC": f"{numbers['main_output_btc']:.4f} BTC",
    },
    {
        "Step": "4. Second output",
        "What happened": "A very small amount was sent to a second output address.",
        "BTC": f"{numbers['second_output_btc']:.8f} BTC",
    },
]
st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

with st.expander("Show shortened input and output tables"):
    st.markdown("**Input addresses**")
    input_table = df_inputs[["Input Address", "Input BTC"]].copy()
    input_table["Address"] = input_table["Input Address"].apply(short_hash)
    input_table["Role"] = input_table["Input Address"].apply(
        lambda x: "Seed address" if x == SEED_ADDRESS else "Other Locky-labelled input"
    )
    input_table = input_table[["Role", "Address", "Input BTC"]].sort_values("Input BTC", ascending=False)
    st.dataframe(input_table, use_container_width=True, hide_index=True)

    st.markdown("**Output addresses**")
    output_table = df_outputs[["Output Address", "Output BTC"]].copy()
    output_table["Address"] = output_table["Output Address"].apply(short_hash)
    output_table = output_table[["Address", "Output BTC"]].sort_values("Output BTC", ascending=False)
    st.dataframe(output_table, use_container_width=True, hide_index=True)

st.subheader("Method note")
st.markdown(
    """
    **Common-input ownership heuristic (CIOH)** groups addresses that are used together as inputs in one transaction.
    The idea is that spending from each input address usually requires control of that address's private key.

    This is useful for clustering, but it is not perfect proof. Exchanges, shared wallets, collaborative transactions
    and privacy tools can weaken the assumption.
    """
)
