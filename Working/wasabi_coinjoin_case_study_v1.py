"""
Wasabi CoinJoin Case Study

This app uses a seed address and Blockstream's public API to find a transaction
with CoinJoin-like structure, then explains it in beginner-friendly language.

Important wording:
- This is NOT attribution proof.
- This does NOT prove the address belongs to Locky, Wasabi, or a mixer operator.
- It shows transaction structure that looks consistent with CoinJoin-style privacy use.
"""

import time
from datetime import datetime
from collections import Counter

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Fixed case settings
# -----------------------------
CASE_NAME = "Wasabi CoinJoin Mixer Case Study"
SEED_ADDRESS = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"
REQUEST_TIMEOUT_SECONDS = 25
BLOCKSTREAM_BASE_URL = "https://blockstream.info/api"

# Keep the graph readable. CoinJoin transactions can be huge.
MAX_GRAPH_INPUTS = 18
MAX_GRAPH_OUTPUTS = 22
SATOSHIS_PER_BTC = 100_000_000


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
    return value / SATOSHIS_PER_BTC


def short_text(value, left=10, right=8):
    """Shorten long txids/addresses for table display."""
    value = str(value)
    if len(value) <= left + right + 3:
        return value
    return f"{value[:left]}...{value[-right:]}"


def is_bitcoin_address(value):
    """Return True when a graph node looks like a Bitcoin address."""
    return str(value).startswith(("1", "3", "bc1"))


@st.cache_data(show_spinner=False)
def get_json(url):
    """Fetch JSON from Blockstream with simple error handling."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def get_address_transactions(address, max_pages=4):
    """Fetch confirmed transactions for an address using Blockstream pagination."""
    all_txs = []
    last_seen_txid = None

    for _ in range(max_pages):
        if last_seen_txid:
            url = f"{BLOCKSTREAM_BASE_URL}/address/{address}/txs/chain/{last_seen_txid}"
        else:
            url = f"{BLOCKSTREAM_BASE_URL}/address/{address}/txs/chain"

        txs = get_json(url)
        if not txs:
            break

        all_txs.extend(txs)
        last_seen_txid = txs[-1]["txid"]

        if len(txs) < 25:
            break

        time.sleep(0.15)

    return all_txs


@st.cache_data(show_spinner=False)
def get_transaction(txid):
    """Fetch one transaction by txid."""
    return get_json(f"{BLOCKSTREAM_BASE_URL}/tx/{txid}")


def tx_date(tx):
    """Return a readable transaction date."""
    block_time = tx.get("status", {}).get("block_time")
    if not block_time:
        return "Unconfirmed / unknown"
    return datetime.utcfromtimestamp(block_time).strftime("%d %b %Y")


def build_input_output_tables(tx):
    """Build simple input and output tables for one Bitcoin transaction."""
    input_rows = []
    output_rows = []
    txid = tx.get("txid")

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


def find_equal_output_groups(df_outputs, min_group_size=3):
    """Find repeated output values. Equal outputs are the clearest CoinJoin clue."""
    if df_outputs.empty:
        return pd.DataFrame(columns=["Output BTC", "Count", "Total BTC"])

    grouped = (
        df_outputs.groupby("Output Value", as_index=False)
        .agg(Count=("Output Address", "count"), Total_Sats=("Output Value", "sum"))
        .sort_values(["Count", "Output Value"], ascending=[False, False])
    )
    grouped = grouped[grouped["Count"] >= min_group_size].copy()
    grouped["Output BTC"] = grouped["Output Value"].apply(sats_to_btc)
    grouped["Total BTC"] = grouped["Total_Sats"].apply(sats_to_btc)
    return grouped[["Output BTC", "Count", "Total BTC"]].reset_index(drop=True)


def score_coinjoin_candidate(tx):
    """Score a transaction for CoinJoin-like structure."""
    df_inputs, df_outputs = build_input_output_tables(tx)
    input_count = len(df_inputs)
    output_count = len(df_outputs)

    output_values = [v for v in df_outputs["Output Value"].tolist() if v > 0]
    value_counts = Counter(output_values)
    equal_groups = [count for count in value_counts.values() if count >= 3]
    largest_equal_group = max(equal_groups) if equal_groups else 0
    equal_output_count = sum(equal_groups)

    seed_is_input = SEED_ADDRESS in set(df_inputs["Input Address"].dropna())
    seed_is_output = SEED_ADDRESS in set(df_outputs["Output Address"].dropna())

    # This is a teaching score, not a forensic certainty score.
    score = 0
    score += min(input_count, 80) * 0.8
    score += min(output_count, 120) * 0.6
    score += largest_equal_group * 5
    score += equal_output_count * 1.5
    if seed_is_input:
        score += 10
    if seed_is_output:
        score += 3

    return {
        "txid": tx.get("txid"),
        "date": tx_date(tx),
        "input_count": input_count,
        "output_count": output_count,
        "largest_equal_group": largest_equal_group,
        "equal_output_count": equal_output_count,
        "seed_role": "Input" if seed_is_input else "Output" if seed_is_output else "Related",
        "score": score,
    }


def choose_best_coinjoin_candidate(address_txs):
    """Pick the strongest CoinJoin-like transaction from the seed address history."""
    if not address_txs:
        return None, pd.DataFrame()

    scored_rows = [score_coinjoin_candidate(tx) for tx in address_txs]
    scored = pd.DataFrame(scored_rows).sort_values("score", ascending=False).reset_index(drop=True)
    best_txid = scored.loc[0, "txid"]
    best_tx = next(tx for tx in address_txs if tx.get("txid") == best_txid)
    return best_tx, scored


def calculate_case_numbers(df_inputs, df_outputs, equal_groups):
    """Calculate key numbers for metric cards."""
    seed_input_btc = df_inputs.loc[df_inputs["Input Address"] == SEED_ADDRESS, "Input BTC"].sum()
    seed_output_btc = df_outputs.loc[df_outputs["Output Address"] == SEED_ADDRESS, "Output BTC"].sum()
    largest_equal_group = int(equal_groups["Count"].max()) if not equal_groups.empty else 0
    strongest_equal_btc = float(equal_groups.sort_values("Count", ascending=False).iloc[0]["Output BTC"]) if not equal_groups.empty else 0

    return {
        "input_count": len(df_inputs),
        "output_count": len(df_outputs),
        "total_input_btc": df_inputs["Input BTC"].sum(),
        "total_output_btc": df_outputs["Output BTC"].sum(),
        "seed_input_btc": seed_input_btc,
        "seed_output_btc": seed_output_btc,
        "largest_equal_group": largest_equal_group,
        "strongest_equal_btc": strongest_equal_btc,
    }


def build_coinjoin_graph(df_inputs, df_outputs, txid):
    """Build a readable graph: many inputs -> one transaction -> repeated outputs."""
    G = nx.DiGraph()
    tx_node = "CoinJoin-like transaction"

    # Keep the graph readable by showing the seed and the largest inputs.
    graph_inputs = df_inputs.copy()
    graph_inputs["Is Seed"] = graph_inputs["Input Address"] == SEED_ADDRESS
    graph_inputs = graph_inputs.sort_values(["Is Seed", "Input BTC"], ascending=[False, False]).head(MAX_GRAPH_INPUTS)

    # Prefer outputs from the largest equal-output group, because that is the main visual clue.
    output_value_counts = df_outputs["Output Value"].value_counts()
    repeated_values = output_value_counts[output_value_counts >= 3]

    if not repeated_values.empty:
        main_repeated_value = repeated_values.index[0]
        repeated_outputs = df_outputs[df_outputs["Output Value"] == main_repeated_value].head(MAX_GRAPH_OUTPUTS)
        other_outputs = df_outputs[df_outputs["Output Value"] != main_repeated_value].sort_values("Output BTC", ascending=False).head(4)
        graph_outputs = pd.concat([repeated_outputs, other_outputs], ignore_index=True)
    else:
        graph_outputs = df_outputs.sort_values("Output BTC", ascending=False).head(MAX_GRAPH_OUTPUTS)

    for _, row in graph_inputs.iterrows():
        address = row["Input Address"]
        if pd.notna(address):
            G.add_edge(address, tx_node, value=row["Input BTC"], edge_type="input")

    for _, row in graph_outputs.iterrows():
        address = row["Output Address"]
        if pd.notna(address):
            G.add_edge(tx_node, address, value=row["Output BTC"], edge_type="output")

    return G, tx_node


def draw_coinjoin_graph(G, tx_node):
    """Draw one compelling network graph."""
    fig, ax = plt.subplots(figsize=(13.5, 7.5))

    input_nodes = [n for n in G.nodes() if G.has_edge(n, tx_node)]
    output_nodes = [n for n in G.nodes() if G.has_edge(tx_node, n)]

    pos = {}
    if input_nodes:
        input_layout = nx.circular_layout(input_nodes, scale=2.7, center=(-2.3, 0))
        pos.update(input_layout)

    pos[tx_node] = (0.9, 0)

    if output_nodes:
        output_layout = nx.circular_layout(output_nodes, scale=2.8, center=(4.0, 0))
        pos.update(output_layout)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")
            node_sizes.append(900)
        elif node == tx_node:
            node_colours.append("#111827")
            node_sizes.append(1150)
        elif node in input_nodes:
            node_colours.append("#93c5fd")
            node_sizes.append(520)
        elif node in output_nodes:
            node_colours.append("#22c55e")
            node_sizes.append(520)
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
        arrowsize=14,
        width=1.25,
        alpha=0.9,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#93c5fd", label="Input address / participant input"),
        mpatches.Patch(color="#111827", label="Shared transaction"),
        mpatches.Patch(color="#22c55e", label="Output address / possible participant output"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Wasabi-style CoinJoin structure: many inputs, many outputs, repeated output amounts", pad=18)
    ax.axis("off")
    return fig


def build_display_table(df, address_col, btc_col, role_func=None):
    """Build a clean table using full addresses."""
    table = df[[address_col, btc_col]].copy()
    table = table.rename(columns={address_col: "Address", btc_col: "BTC"})
    if role_func is not None:
        table["Role"] = table["Address"].apply(role_func)
        table = table[["Role", "Address", "BTC"]]
    return table.sort_values("BTC", ascending=False).reset_index(drop=True)


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A beginner-friendly case study showing CoinJoin-like structure using public Bitcoin data.")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
            This case study starts from the seed address:<br>
            <code>{SEED_ADDRESS}</code>
        </p>
        <p>
            The app checks the address's confirmed transaction history using the Blockstream API,
            then picks the transaction with the strongest CoinJoin-like structure.
        </p>
        <p>
            The goal is education, not accusation. We are looking at transaction structure only.
            We are not proving who controlled the wallet.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.header("How the analysis works")

st.markdown(
    """
    <div class="case-card">
        <h3>CoinJoin-like pattern</h3>
        <p>
            A CoinJoin transaction combines coins from multiple people into one shared transaction.
            This can make tracing harder because the transaction has many inputs and many outputs.
        </p>
        <p>
            The clearest beginner-friendly clue is repeated output amounts.
            For example, if many outputs have exactly the same BTC amount, those outputs may be
            acting like privacy-set outputs.
        </p>
        <p class="small-note">
            This is different from the Locky CIOH case. CIOH says multiple inputs may belong to one controller.
            CoinJoin is the warning label: many inputs together may instead mean a collaborative privacy transaction.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading seed address history from Blockstream..."):
        address_txs = get_address_transactions(SEED_ADDRESS, max_pages=4)
        selected_tx, candidate_table = choose_best_coinjoin_candidate(address_txs)

    if selected_tx is None:
        st.error("No confirmed transactions were found for this address.")
        st.stop()

    # Re-fetch selected transaction by txid to keep the case data clean and complete.
    selected_tx = get_transaction(selected_tx["txid"])
    df_inputs, df_outputs = build_input_output_tables(selected_tx)
    equal_groups = find_equal_output_groups(df_outputs)
    numbers = calculate_case_numbers(df_inputs, df_outputs, equal_groups)

except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch Bitcoin data from Blockstream: {exc}")
    st.stop()

st.subheader("Selected transaction")
st.write(
    "The app selected this transaction because it has the strongest CoinJoin-like structure in the seed address history."
)

st.code(selected_tx["txid"], language="text")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Inputs", numbers["input_count"])
col2.metric("Outputs", numbers["output_count"])
col3.metric("BTC in", f"{numbers['total_input_btc']:.8f}")
col4.metric("Largest equal group", numbers["largest_equal_group"])
col5.metric("Repeated amount", f"{numbers['strongest_equal_btc']:.8f} BTC")

st.markdown(
    f"""
    <div class="case-card">
    <h3>Plain English summary</h3>
    <p>
    On <strong>{tx_date(selected_tx)}</strong>, the seed address appeared in a transaction with
    <strong>{numbers['input_count']}</strong> inputs and <strong>{numbers['output_count']}</strong> outputs.
    </p>
    <p>
    This shape is very different from a normal simple payment. It looks more like a shared transaction,
    where many coins are combined and then split back out.
    </p>
    <p>
    The strongest structural clue is the equal-output pattern: the biggest repeated-output group contains
    <strong>{numbers['largest_equal_group']}</strong> outputs of about
    <strong>{numbers['strongest_equal_btc']:.8f} BTC</strong> each.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. CoinJoin-like network graph")
st.write(
    "This graph keeps the story simple: many input addresses feed one shared transaction, then many outputs leave it. "
    "The seed address is red. The shared transaction is black."
)
coinjoin_graph, tx_node = build_coinjoin_graph(df_inputs, df_outputs, selected_tx["txid"])
st.pyplot(draw_coinjoin_graph(coinjoin_graph, tx_node))

st.subheader("2. Structural evidence")
st.write(
    "These are the repeated output amounts. In CoinJoin-style transactions, repeated amounts matter because they make outputs harder to distinguish from each other."
)

if equal_groups.empty:
    st.warning("No repeated output groups of 3 or more were found in this selected transaction.")
else:
    st.dataframe(equal_groups, use_container_width=True, hide_index=True)

st.subheader("3. Transaction summary")
seed_role = "input" if numbers["seed_input_btc"] > 0 else "output" if numbers["seed_output_btc"] > 0 else "related address"
seed_btc = numbers["seed_input_btc"] if numbers["seed_input_btc"] > 0 else numbers["seed_output_btc"]

summary_rows = [
    {
        "Step": "1. Starting point",
        "What happened": f"The seed address appears as a transaction {seed_role}.",
        "BTC": f"{seed_btc:.8f} BTC linked to seed role",
    },
    {
        "Step": "2. Shared transaction",
        "What happened": f"The transaction combines {numbers['input_count']} inputs and creates {numbers['output_count']} outputs.",
        "BTC": f"{numbers['total_input_btc']:.8f} BTC total input",
    },
    {
        "Step": "3. Equal-output clue",
        "What happened": "Several outputs have exactly the same BTC value.",
        "BTC": f"Largest group: {numbers['largest_equal_group']} × {numbers['strongest_equal_btc']:.8f} BTC",
    },
    {
        "Step": "4. Interpretation",
        "What happened": "This is consistent with CoinJoin-style privacy behaviour, but it is not proof of ownership or criminal activity.",
        "BTC": "N/A",
    },
]
st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

st.subheader("Why this matters for tracing")
st.info(
    "In the Locky CIOH case, many inputs spent together helped us form a cluster. "
    "In a CoinJoin-style case, the same 'many inputs together' pattern is a warning sign. "
    "It may be a collaborative transaction, so we should avoid claiming that all input addresses belong to one person."
)

with st.expander("Show candidate transactions from the seed address"):
    display_candidates = candidate_table.copy()
    display_candidates["txid"] = display_candidates["txid"].apply(short_text)
    st.dataframe(display_candidates, use_container_width=True, hide_index=True)

with st.expander("Show full input and output address tables"):
    st.markdown("**Input addresses**")
    input_table = build_display_table(
        df_inputs,
        "Input Address",
        "Input BTC",
        role_func=lambda x: "Seed address" if x == SEED_ADDRESS else "Other input address",
    )
    st.dataframe(input_table, use_container_width=True, hide_index=True)

    st.markdown("**Output addresses**")
    output_value_counts = df_outputs["Output Value"].value_counts().to_dict()
    output_table = build_display_table(
        df_outputs,
        "Output Address",
        "Output BTC",
        role_func=lambda x: "Seed address" if x == SEED_ADDRESS else "Output address",
    )
    st.dataframe(output_table, use_container_width=True, hide_index=True)

st.subheader("Safe wording for the report")
st.markdown(
    """
    <div class="case-card">
    <p>
    This case study shows a transaction with CoinJoin-like structural patterns, including many inputs,
    many outputs and repeated output amounts. These features are consistent with Wasabi-style CoinJoin
    behaviour because CoinJoin transactions are designed to make ownership links harder to follow.
    However, this analysis does not prove that any address belongs to Locky, Wasabi, a mixer operator,
    or a specific person. It only demonstrates why privacy transactions require extra caution in
    blockchain tracing.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("References")
with st.expander("Show references and data sources"):
    st.markdown(
        """
        Blockstream (n.d.) *Blockstream Explorer API documentation*. Available at: https://blockstream.info/explorer-api (Accessed: 26 May 2026).

        Blockstream/esplora (n.d.) *API.md*. Available at: https://github.com/Blockstream/esplora/blob/master/API.md (Accessed: 26 May 2026).

        Wasabi Wallet (n.d.) *CoinJoin documentation*. Available at: https://docs.wasabiwallet.io/using-wasabi/CoinJoin.html (Accessed: 26 May 2026).
        """
    )
