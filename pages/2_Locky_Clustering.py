"""
Locky Ransomware Clustering Case Study

This Streamlit app demonstrates the common-input ownership heuristic (CIOH)
using a Locky-labelled Bitcoin consolidation transaction.

The app is intentionally hardcoded for this case study so the display stays
clear and consistent for assessment/demo purposes.
"""

import time
from datetime import datetime
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed case settings
# -----------------------------
CASE_NAME = "Locky ransomware: clustering"
SEED_ADDRESS = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"
CIOH_TXID = "275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"
FOLLOW_ON_TXID = "69affd84d73a7bbf644fe9defa18bab740b76487c07b636a6bb4a50689d8e8e3"
EIGHTY_BTC_OUTPUT_ADDRESS = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"
REQUEST_TIMEOUT_SECONDS = 20


# These are the 30 input addresses in the CIOH transaction.
# These 30 addresses appear in the public Ransomwhere dataset under the Locky ransomware family.
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
    .small-note {font-size: 0.92rem; color: #666;}
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


def full_address(value):
    """Return the full address for display."""
    return value


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
        mpatches.Patch(color="#93c5fd", label="Other Locky-associated input address"),
        mpatches.Patch(color="#111827", label="Shared Bitcoin transaction"),
        mpatches.Patch(color="#22c55e", label="Output address"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Common-input ownership heuristic: 30 Locky-associated inputs spent together", pad=18)
    ax.axis("off")
    return fig


def build_flow_graph(df_inputs, df_outputs):
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


def draw_flow_graph(G):
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


def build_follow_on_graph(df_inputs, df_outputs):
    """Build a graph for the later transaction where the 80 BTC output was spent again."""
    G = nx.DiGraph()
    tx_node = FOLLOW_ON_TXID

    for _, row in df_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            G.add_edge(address, tx_node, value=row["Input BTC"], edge_type="input")

    for _, row in df_outputs.iterrows():
        address = row["Output Address"]
        if pd.notna(address):
            G.add_edge(tx_node, address, value=row["Output BTC"], edge_type="output")

    return G


def draw_follow_on_graph(G):
    """Draw the later 512.999 BTC aggregation transaction."""
    fig, ax = plt.subplots(figsize=(13, 6))

    pos = nx.spring_layout(G, k=0.85, seed=24)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == EIGHTY_BTC_OUTPUT_ADDRESS:
            node_colours.append("#f97316")  # orange
            node_sizes.append(900)
        elif node == FOLLOW_ON_TXID:
            node_colours.append("#111827")  # black
            node_sizes.append(950)
        elif is_bitcoin_address(node):
            node_colours.append("#93c5fd")
            node_sizes.append(560)
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
        mpatches.Patch(color="#f97316", label="80 BTC output from the Locky CIOH transaction"),
        mpatches.Patch(color="#93c5fd", label="Other later input/output address"),
        mpatches.Patch(color="#111827", label="Later aggregation transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Follow-on trace: 80 BTC output later joins a 512.999 BTC aggregation", pad=18)
    ax.axis("off")
    return fig

def get_tx_date(txid):
    """Fetch transaction confirmation date from Blockstream."""
    try:
        tx = requests.get(
            f"https://blockstream.info/api/tx/{txid}",
            timeout=20
        ).json()

        ts = tx["status"]["block_time"]
        return datetime.utcfromtimestamp(ts).strftime("%d %b %Y")

    except:
        return "Unknown"

def build_display_table(df, address_col, btc_col, role_func=None):
    """Build a table using full addresses, not shortened addresses."""
    table = df[[address_col, btc_col]].copy()
    table = table.rename(columns={address_col: "Address", btc_col: "BTC"})
    if role_func is not None:
        table["Role"] = table["Address"].apply(role_func)
        table = table[["Role", "Address", "BTC"]]
    return table.sort_values("BTC", ascending=False).reset_index(drop=True)


# -----------------------------
# App UI
# -----------------------------
st.title("₿ Locky ransomware: clustering")

st.caption(
    "Follow the money from a known Locky address and see how clustering can help investigators clock related Bitcoin addresses."
)

st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
            Locky was one of the biggest ransomware families of its time. Victims were instructed to pay a ransom in Bitcoin,
            creating a trail that investigators could later examine on the blockchain.
        </p>
        <p>
            This case study begins with a Bitcoin address associated with Locky and follows the money through a larger
            consolidation transaction. By looking at which addresses were used together, investigators can build a picture of
            which wallets may have been controlled by the same operator group.
        </p>
        <p>
            The goal is not to prove ownership. The goal is to identify transaction patterns that deserve a closer look.
            This is where clustering becomes a useful starting point for blockchain hide and seek.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

st.header("Following the money")

st.markdown(
    """
    <div class="case-card">
        <h3>Common-input ownership heuristic (CIOH)</h3>
        <p>
            The Common Input Ownership Heuristic is one of the classic blockchain tracing vibe checks.
            If multiple Bitcoin addresses are used together as inputs in the same transaction, investigators may infer
            that the same person, wallet or group controls them.
        </p>
        <p>
            The idea is simple: spending from an address normally requires access to its private key. Like all heuristics,
            this is a clue rather than proof, but it can be a strong place to start when trying to clock related addresses.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
st.write("")
st.write("")

try:
    with st.spinner("Loading Locky transaction data from Blockstream..."):
        cioh_tx = get_transaction(CIOH_TXID)
        follow_on_tx = get_transaction(FOLLOW_ON_TXID)
        df_inputs, df_outputs = build_input_output_tables(cioh_tx)
        df_follow_inputs, df_follow_outputs = build_input_output_tables(follow_on_tx)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch Bitcoin data from Blockstream: {exc}")
    st.stop()

numbers = calculate_case_numbers(df_inputs, df_outputs)
follow_numbers = calculate_case_numbers(df_follow_inputs, df_follow_outputs)

st.info(
    f"""
**What should you clock**

• Many addresses spent together

• One dominant output

• Very small change output

• Strong clustering signal
"""
)

st.markdown(
    """
    <div class="case-card">
    <h3>What does not pass the vibe check?</h3>
    <p>
    Thirty Locky-associated addresses were used together as inputs in one Bitcoin transaction.
    Under the Common Input Ownership Heuristic, this is a strong clue that the addresses may have been
    controlled by the same wallet or operator group.
    </p>
    <p>
    This does not prove who controlled the addresses, but it is unusual enough to deserve a closer look.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Following the money")
st.write(
    "This is the main visual story: many Locky-associated input addresses are combined in one transaction, then almost all of the Bitcoin moves to one 80 BTC output address."
)
flow_graph = build_flow_graph(df_inputs, df_outputs)
st.pyplot(draw_flow_graph(flow_graph))




st.subheader("2. Building the cluster")
st.write(
    "This graph shows why the transaction is useful for clustering. The seed address and the other Locky-associated input addresses were spent together in the same transaction."
)

st.info(
    "Before the main consolidation event, the seed address received 3 BTC from a transaction funded by three separate input addresses. That is interesting, but the stronger clue comes later, when 30 Locky-associated addresses are spent together in one transaction."
)
cioh_graph, shared_tx_node = build_cioh_graph(df_inputs, df_outputs)
st.pyplot(draw_cioh_graph(cioh_graph, shared_tx_node))

st.subheader("3. Where did the 80 BTC go next?")
st.write(
    "The 80 BTC output address later appeared as an input in a larger aggregation transaction. "
    "At this point, the trail is still visible, but attribution becomes less certain because the later addresses are not labelled in the ransomware dataset."
)
follow_graph = build_follow_on_graph(df_follow_inputs, df_follow_outputs)
st.pyplot(draw_follow_on_graph(follow_graph))

st.info(
    f"""
**What happened next?**

The trail does not end here. The 80 BTC output later appeared in a much larger transaction involving several additional inputs.
"""
)


st.subheader("Where the trail starts to get messy")
trace_rows = [
    {
        "Step": "1",
        "Date": get_tx_date("275937c2c30fbdf778390cb33a1ca1236c824c26a0a89af34e540c18d692d648"),
        "From address": "30 Locky-associated addresses",
        "To address": "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E",
        "BTC moved": "80 BTC",
        "Interpretation": "Locky-linked funds are consolidated",
    },
    {
        "Step": "2",
        "Date": get_tx_date("69affd84d73a7bbf644fe9defa18bab740b76487c07b636a6bb4a50689d8e8e3"),
        "From address": "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E (+ 6 other inputs)",
        "To address": "16YhEbMcksa6zgf2rjcAUWy7fZ9TkgFNXF",
        "BTC moved": "500 BTC",
        "Interpretation": "Funds move into broader unattributed infrastructure",
    },
    {
        "Step": "3",
        "Date": get_tx_date("2db4093a6c4dde3cf2aeffb093f7bfa9f64d45ba0cc41fb437b1d98004b45f31"),
        "From address": "16YhEbMcksa6zgf2rjcAUWy7fZ9TkgFNXF",
        "To address": "17e2WMCFReEsRev8nmC9SdbjDYfXjkGcMM",
        "BTC moved": "100 BTC",
        "Interpretation": "First visible redistribution split",
    },
    {
        "Step": "4",
        "Date": get_tx_date("2db4093a6c4dde3cf2aeffb093f7bfa9f64d45ba0cc41fb437b1d98004b45f31"),
        "From address": "16YhEbMcksa6zgf2rjcAUWy7fZ9TkgFNXF",
        "To address": "17VSgeazX2nz4kfEjG5o5Tt6TUqHkWXs7U",
        "BTC moved": "399.99992101 BTC",
        "Interpretation": "Remaining funds keep moving",
    },
    {
        "Step": "5",
        "Date": get_tx_date("09c090cbe7be5951bcbc6f3c3b4a82db27f948f1ffa003bf1cde353a4d58811f"),
        "From address": "17VSgeazX2nz4kfEjG5o5Tt6TUqHkWXs7U",
        "To address": "1GMh6Qq79ZR4AQEeTMWRz2s1uP2NJ2YAeg",
        "BTC moved": "199.99984202 BTC",
        "Interpretation": "Further redistribution",
    },
    {
        "Step": "6",
        "Date": get_tx_date("09c090cbe7be5951bcbc6f3c3b4a82db27f948f1ffa003bf1cde353a4d58811f"),
        "From address": "17VSgeazX2nz4kfEjG5o5Tt6TUqHkWXs7U",
        "To address": "1NKi9AK5R3Y8DQQgrwneCzDz5QkpUkLjHJ",
        "BTC moved": "200 BTC",
        "Interpretation": "Further redistribution",
    },
]

st.dataframe(pd.DataFrame(trace_rows), use_container_width=True, hide_index=True)
st.caption("Beyond the original Locky-associated cluster, the money trail is still visible, but attribution becomes less certain because the later wallets were not labelled in the ransomware dataset.")

st.markdown(
    """
    <div class="case-card">
    <h3>Follow-on trace note</h3>
    <p>
    The address <code>1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E</code> received the 80 BTC output from the Locky CIOH transaction.
    It was later spent together with six other inputs in a larger transaction totalling 512.99958568 BTC.
    The largest later output was 500 BTC.
    </p>
    <p class="small-note">
    This is a good example of the blockchain hide and seek problem: the funds can still be followed, but it becomes harder to know who controls the later wallets.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("Show follow-on input and output tables"):
    st.markdown("**Follow-on input addresses**")
    follow_input_table = build_display_table(
        df_follow_inputs,
        "Input Address",
        "Input BTC",
        role_func=lambda x: "80 BTC output address from Locky transaction" if x == EIGHTY_BTC_OUTPUT_ADDRESS else "Other follow-on input",
    )
    st.dataframe(follow_input_table, use_container_width=True, hide_index=True)

    st.markdown("**Follow-on output addresses**")
    follow_output_table = build_display_table(df_follow_outputs, "Output Address", "Output BTC")
    st.dataframe(follow_output_table, use_container_width=True, hide_index=True)

st.subheader("Case study summary")
summary_rows = [
    {
        "Step": "1. Starting point",
        "What happened": "The seed address appears as one of 30 Locky-associated inputs in the transaction.",
        "BTC": f"{numbers['seed_contribution']:.4f} BTC from the seed",
    },
    {
        "Step": "2. CIOH evidence",
        "What happened": "The 30 input addresses were spent together, creating a strong clustering clue.",
        "BTC": f"{numbers['total_input_btc']:.4f} BTC combined",
    },
    {
        "Step": "3. Main output",
        "What happened": "Most of the combined Bitcoin moved to output address 1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E.",
        "BTC": f"{numbers['main_output_btc']:.4f} BTC",
    },
    {
        "Step": "4. Second output",
        "What happened": "A very small amount was sent to output address 12p2CcaDixL2FCMBzxzfMhPwufMohDbTmH.",
        "BTC": f"{numbers['second_output_btc']:.8f} BTC",
    },
]
st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

with st.expander("Show full input and output address tables"):
    st.markdown("**Input addresses**")
    input_table = build_display_table(
        df_inputs,
        "Input Address",
        "Input BTC",
        role_func=lambda x: "Seed address" if x == SEED_ADDRESS else "Other Locky-associated input",
    )
    st.dataframe(input_table, use_container_width=True, hide_index=True)

    st.markdown("**Output addresses**")
    output_table = build_display_table(df_outputs, "Output Address", "Output BTC")
    st.dataframe(output_table, use_container_width=True, hide_index=True)


st.subheader("References")

with st.expander("Show references and data sources"):
    st.markdown(
        """

        Blockstream (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/explorer-api (Accessed: 24 May 2026).

        Cable J (2024) *Ransomwhere: A Crowdsourced Ransomware Payment Dataset (1.1.0) [Data set]*. Available at: https://doi.org/10.5281/zenodo.6512122 (Accessed: 24 May 2026).

        SANS Institute (2017) *Tracking Bitcoin Transactions on the Blockchain - SANS DFIR Summit 2017*. Available at: https://www.youtube.com/watch?v=1iwsouV8ouQ (Accessed: 27 February 2026).
        """
    )