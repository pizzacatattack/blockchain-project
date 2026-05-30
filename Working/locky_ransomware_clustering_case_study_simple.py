"""Simple Streamlit case study for the Locky ransomware clustering example.

This app is designed for a non-technical viewer. It keeps the addresses fixed,
uses simple wording, and focuses on the main question:

1. How much did the seed address send to the main cluster transaction?
2. How much BTC was combined in that main transaction?
3. How much BTC went to each of the two output addresses?

Important: common-input clustering is a clue, not proof of real-world identity.
"""

import time
from itertools import combinations

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


def build_input_clusters(df_inputs):
    """Group addresses that were used together as inputs."""
    clusters = []

    if df_inputs.empty:
        return clusters

    for _, group in df_inputs.groupby("Transaction ID"):
        addresses = set(group["Input Address"].dropna().unique())
        if len(addresses) > 1:
            clusters.append(addresses)

    return clusters


def merge_overlapping_sets(list_of_sets):
    """Merge clusters that share at least one address."""
    sets = [set(s) for s in list_of_sets]

    changed = True
    while changed:
        changed = False
        new_sets = []

        while sets:
            first, *rest = sets
            first = set(first)
            still_rest = []

            for s in rest:
                if first & s:
                    first |= s
                    changed = True
                else:
                    still_rest.append(s)

            new_sets.append(first)
            sets = still_rest

        sets = new_sets

    return sets


def build_clusters_dataframe(merged_clusters):
    """Turn clusters into a table."""
    rows = []

    for i, cluster in enumerate(merged_clusters, start=1):
        for address in cluster:
            rows.append({
                "Cluster ID": i,
                "Address": address,
                "Cluster Size": len(cluster),
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            by=["Cluster Size", "Cluster ID", "Address"],
            ascending=[False, True, True],
        ).reset_index(drop=True)

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


def calculate_case_numbers(seed_outputs, main_inputs, main_outputs):
    """Calculate the key amounts shown at the top of the app."""
    seed_to_main_btc = seed_outputs[
        seed_outputs["Output Address"] == MAIN_CLUSTER_ADDRESS
    ]["Output BTC"].sum()

    main_combined_btc = main_inputs["Input BTC"].sum() if main_inputs is not None else 0

    return {
        "seed_to_main_btc": seed_to_main_btc,
        "main_combined_btc": main_combined_btc,
        "output_count": len(main_outputs) if main_outputs is not None else 0,
    }


def build_simple_flow_graph(seed_txid, main_txid, main_outputs):
    """Build a small graph that only shows the case story."""
    graph = nx.DiGraph()

    graph.add_edge(SEED_ADDRESS, seed_txid, value="seed input")
    graph.add_edge(seed_txid, MAIN_CLUSTER_ADDRESS, value="seed to main")
    graph.add_edge(MAIN_CLUSTER_ADDRESS, main_txid, value="main input")

    for _, row in main_outputs.iterrows():
        graph.add_edge(main_txid, row["Output Address"], value=row["Output BTC"])

    return graph


def draw_simple_flow_graph(graph):
    """Draw the simplified graph with no node text labels."""
    fig, ax = plt.subplots(figsize=(12, 6))

    pos = nx.spring_layout(graph, seed=42, k=0.9)

    node_colours = []
    node_sizes = []

    for node in graph.nodes():
        if node == SEED_ADDRESS:
            node_colours.append("#ef4444")
            node_sizes.append(900)
        elif node == MAIN_CLUSTER_ADDRESS:
            node_colours.append("#8b5cf6")
            node_sizes.append(950)
        elif is_bitcoin_address(node):
            node_colours.append("#93c5fd")
            node_sizes.append(650)
        else:
            node_colours.append("#d1d5db")
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
        arrowsize=18,
        width=1.8,
        alpha=0.9,
    )

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed address"),
        mpatches.Patch(color="#8b5cf6", label="Main cluster address"),
        mpatches.Patch(color="#93c5fd", label="Output address"),
        mpatches.Patch(color="#d1d5db", label="Bitcoin transaction"),
    ]

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title("Simple BTC flow: seed address → main cluster → two outputs", pad=18)
    ax.axis("off")
    return fig


def build_cluster_graph(merged_clusters):
    """Build a graph connecting addresses that were used together as inputs."""
    graph = nx.Graph()

    for cluster in merged_clusters:
        for address_a, address_b in combinations(list(cluster), 2):
            graph.add_edge(address_a, address_b)

    return graph


def draw_cluster_graph(cluster_graph):
    """Draw the cluster graph with legend only and no address labels."""
    fig, ax = plt.subplots(figsize=(12, 7))

    if cluster_graph.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No cluster found", ha="center", va="center")
        ax.axis("off")
        return fig

    pos = nx.spring_layout(cluster_graph, seed=42, k=0.45)

    nx.draw(
        cluster_graph,
        pos,
        ax=ax,
        with_labels=False,
        node_size=520,
        node_color="#8b5cf6",
        edge_color="#6b7280",
        alpha=0.85,
    )

    ax.legend(
        handles=[
            mpatches.Patch(color="#8b5cf6", label="Address in the likely cluster"),
            mpatches.Patch(color="#6b7280", label="Used together in one transaction"),
        ],
        loc="best",
    )
    ax.set_title("Cluster view: addresses used together", pad=18)
    ax.axis("off")
    return fig


def analyse_case():
    """Run the fixed Locky case study."""
    seed_txs = get_all_transactions(SEED_ADDRESS)
    main_txs = get_all_transactions(MAIN_CLUSTER_ADDRESS)

    all_txs = seed_txs + main_txs
    df_inputs = build_transaction_inputs(all_txs).drop_duplicates()
    df_outputs = build_transaction_outputs(all_txs).drop_duplicates()

    seed_outputs = build_transaction_outputs(seed_txs)
    small_clusters = build_input_clusters(df_inputs)
    merged_clusters = merge_overlapping_sets(small_clusters)
    df_clusters = build_clusters_dataframe(merged_clusters)

    main_spend = find_main_spend_transaction(df_inputs, df_outputs)

    if main_spend is None:
        main_inputs = pd.DataFrame()
        main_outputs = pd.DataFrame()
        main_txid = None
    else:
        main_inputs = main_spend["inputs"]
        main_outputs = main_spend["outputs"].copy()
        main_txid = main_spend["txid"]

    numbers = calculate_case_numbers(seed_outputs, main_inputs, main_outputs)

    seed_to_main_rows = seed_outputs[
        seed_outputs["Output Address"] == MAIN_CLUSTER_ADDRESS
    ]
    seed_txid = seed_to_main_rows["Transaction ID"].iloc[0] if not seed_to_main_rows.empty else "Seed transaction"

    return {
        "df_inputs": df_inputs,
        "df_outputs": df_outputs,
        "df_clusters": df_clusters,
        "merged_clusters": merged_clusters,
        "main_inputs": main_inputs,
        "main_outputs": main_outputs,
        "main_txid": main_txid,
        "seed_txid": seed_txid,
        "numbers": numbers,
    }


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A simple Bitcoin flow example using common-input clustering.")

st.markdown(
    """
    <div class="case-card">
    <h3>What this page shows</h3>
    <p>
    This page follows one Locky-related Bitcoin address. The goal is not to name a real person.
    The goal is to show how Bitcoin addresses can be linked when they are used together in the same transaction.
    </p>
    <p>
    In plain English: if lots of addresses help pay for one Bitcoin transaction, they may belong to the same wallet or group.
    That is a useful clue, but it is not perfect proof.
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
df_clusters = results["df_clusters"]
merged_clusters = results["merged_clusters"]

col1, col2, col3 = st.columns(3)
col1.metric("Seed sent to main cluster", f"{numbers['seed_to_main_btc']:.8f} BTC")
col2.metric("Main transaction combined", f"{numbers['main_combined_btc']:.8f} BTC")
col3.metric("Main transaction outputs", numbers["output_count"])

st.markdown(
    """
    <div class="case-card">
    <h3>The story in one paragraph</h3>
    <p>
    The seed address sent BTC into a bigger transaction. That bigger transaction combined BTC from many input addresses.
    Because those addresses were used together, we treat them as a likely cluster. The combined BTC was then split into two output addresses.
    </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "Simple summary",
    "Flow diagram",
    "Cluster diagram",
    "Simple tables",
    "Method notes",
])

with tabs[0]:
    st.subheader("Simple summary")
    st.write("This is the main thing a viewer should understand:")

    summary_rows = [
        {
            "Step": "1. Seed address sends BTC",
            "What it means": "The starting address sends BTC into the main cluster transaction.",
            "Amount": f"{numbers['seed_to_main_btc']:.8f} BTC",
        },
        {
            "Step": "2. Main transaction combines BTC",
            "What it means": "The transaction combines BTC from several input addresses.",
            "Amount": f"{numbers['main_combined_btc']:.8f} BTC",
        },
        {
            "Step": "3. BTC is split into outputs",
            "What it means": "The combined BTC is sent out to two output addresses.",
            "Amount": f"{numbers['output_count']} outputs",
        },
    ]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.info("The cluster is a likely group of related addresses. It is a clue, not a final identity claim.")

with tabs[1]:
    st.subheader("Flow diagram")
    st.write("The arrows show the direction BTC moved. The dots have no text labels so the diagram stays easy to read.")

    if results["main_txid"] is None or main_outputs.empty:
        st.warning("Could not find the main two-output transaction for this case.")
    else:
        flow_graph = build_simple_flow_graph(
            results["seed_txid"],
            results["main_txid"],
            main_outputs,
        )
        st.pyplot(draw_simple_flow_graph(flow_graph))

with tabs[2]:
    st.subheader("Cluster diagram")
    st.write("This shows addresses that were used together as inputs. Used together can mean likely controlled together.")

    cluster_graph = build_cluster_graph(merged_clusters)
    st.pyplot(draw_cluster_graph(cluster_graph))

with tabs[3]:
    st.subheader("Simple tables")

    st.markdown("**Main transaction inputs**")
    st.write("These are the addresses that helped fund the main transaction.")
    if main_inputs.empty:
        st.warning("No main transaction inputs found.")
    else:
        input_table = main_inputs[["Input Address", "Input BTC"]].copy()
        input_table["Address"] = input_table["Input Address"].apply(short_hash)
        input_table = input_table[["Address", "Input BTC"]].sort_values("Input BTC", ascending=False)
        st.dataframe(input_table, use_container_width=True, hide_index=True)

    st.markdown("**Main transaction outputs**")
    st.write("These are the two places the BTC went after being combined.")
    if main_outputs.empty:
        st.warning("No main transaction outputs found.")
    else:
        output_table = main_outputs[["Output Address", "Output BTC"]].copy()
        output_table["Address"] = output_table["Output Address"].apply(short_hash)
        output_table = output_table[["Address", "Output BTC"]].sort_values("Output BTC", ascending=False)
        st.dataframe(output_table, use_container_width=True, hide_index=True)

    with st.expander("Show full cluster address table"):
        if df_clusters.empty:
            st.warning("No cluster rows found.")
        else:
            table = df_clusters.copy()
            table["Short Address"] = table["Address"].apply(short_hash)
            st.dataframe(
                table[["Cluster ID", "Short Address", "Cluster Size"]],
                use_container_width=True,
                hide_index=True,
            )

with tabs[4]:
    st.subheader("Method notes")
    st.markdown(
        """
        **What is clustering?**  
        Clustering means grouping Bitcoin addresses that seem related.

        **Why do we group these addresses?**  
        In Bitcoin, one transaction can use many input addresses. If many addresses are used together to pay for one transaction,
        they may be controlled by the same wallet or same group.

        **What is the warning?**  
        This is not proof of identity. It is only a clue. Some services, exchanges, wallets or privacy tools can make this messy.

        **What should the viewer remember?**  
        The seed address sent BTC into a larger transaction. That transaction combined BTC from several likely related addresses,
        then split the BTC into two outputs.
        """
    )
