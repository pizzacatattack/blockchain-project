"""Investigator-style Streamlit dashboard for the Locky clustering case study.

This app turns the Locky clustering script into an interactive case-study view.
It demonstrates the common-input ownership heuristic by grouping addresses that
appear together as inputs in the same Bitcoin transaction.

Important: this is an educational heuristic demonstration, not forensic proof.
"""

import time
from itertools import combinations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st


# Locky is a well-researched ransomware case from 2016, infected millions of users worldwide
# Seed address here was just used for two transactions
# However, one of those transactions involved 29 other unique input addresses
# When multiple addresses are used for one input, those addresses likely all have the same owner/controlled by the same person or entity
# Used ChatGPT for this, which I will attribute
# Main piece of work for my project will then be the research paper I write to go along with my tool


# -----------------------------
# CONFIG
# -----------------------------
CASE_NAME = "Locky Ransomware"
DEFAULT_SEED_ADDRESS = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"
DEFAULT_TARGET_ADDRESS = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"
REQUEST_TIMEOUT_SECONDS = 20
API_SLEEP_SECONDS = 0.2


# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(
    page_title="Locky Clustering Case Study",
    page_icon="🕵️",
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
    }
    .small-note {font-size: 0.9rem; color: #666;}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Helper functions
# -----------------------------
def sats_to_btc(value):
    """Convert satoshis to BTC.

    Args:
        value: Integer satoshi value from the Blockstream API.

    Returns:
        Float BTC value, or None if the input is missing.
    """
    return value / 100_000_000 if value is not None else None


def is_bitcoin_address(value):
    """Return True when a graph node looks like a Bitcoin address.

    This is only used for visual styling. It is not an attribution method.
    """
    return str(value).startswith(("1", "3", "bc1"))


# -----------------------------
# 1. Get all confirmed transactions for a seed address (e.g. Locky address noted above)
# -----------------------------
@st.cache_data(show_spinner=False)
def get_all_transactions(seed_address):
    """Fetch all confirmed transactions for a Bitcoin address.

    Blockstream returns address transactions in pages. This function keeps
    requesting pages until the returned page has fewer than 25 transactions.

    Args:
        seed_address: Bitcoin address to query.

    Returns:
        List of transaction dictionaries returned by the Blockstream API.
    """
    all_txs = []
    last_seen = None

    while True:
        if last_seen:
            url = f"https://blockstream.info/api/address/{seed_address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{seed_address}/txs/chain"

        res = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        res.raise_for_status()
        data = res.json()

        all_txs.extend(data)

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(API_SLEEP_SECONDS)

    return all_txs


# -----------------------------
# 2. Build transaction_inputs table
# -----------------------------
# All addresses that provided funds for each transaction
def build_transaction_inputs(all_txs):
    """Create a table where each row is one transaction input.

    Inputs show where transaction funding came from. Multi-input transactions
    are the basis for the common-input ownership heuristic used in this case.
    """
    input_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vin in enumerate(tx.get("vin", [])):
            prevout = vin.get("prevout", {})

            input_rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Input Index": i,
                "Input Address": prevout.get("scriptpubkey_address"),
                "Input Value": prevout.get("value")
            })

    df_inputs = pd.DataFrame(input_rows)

    if not df_inputs.empty:
        df_inputs["Timestamp"] = pd.to_datetime(
            df_inputs["Timestamp"], unit="s", errors="coerce"
        )
        df_inputs["Input BTC"] = df_inputs["Input Value"].apply(sats_to_btc)

    return df_inputs


# -----------------------------
# 3. Build transaction_outputs table
# -----------------------------
# All addresses that received funds from each transaction
def build_transaction_outputs(all_txs):
    """Create a table where each row is one transaction output.

    Outputs show where value was sent. This powers the flow graph and one-hop
    tracing tables.
    """
    output_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vout in enumerate(tx.get("vout", [])):
            output_rows.append({
                "Transaction ID": txid,
                "Timestamp": timestamp,
                "Output Index": i,
                "Output Address": vout.get("scriptpubkey_address"),
                "Output Value": vout.get("value")
            })

    df_outputs = pd.DataFrame(output_rows)

    if not df_outputs.empty:
        df_outputs["Timestamp"] = pd.to_datetime(
            df_outputs["Timestamp"], unit="s", errors="coerce"
        )
        df_outputs["Output BTC"] = df_outputs["Output Value"].apply(sats_to_btc)

    return df_outputs


# -----------------------------
# 4. Build small multi-input clusters
#    One set per transaction with >1 unique input address
# -----------------------------
# For each transaction, if it has more than one unique input address, group those addresses together into a cluster
def build_input_clusters(df_inputs):
    """Build small clusters using the common-input ownership heuristic.

    If multiple addresses provide inputs to the same transaction, this app treats
    them as likely common-control candidates. This is a heuristic and should be
    explained as uncertain, not proven identity.
    """
    small_clusters = []

    if df_inputs.empty:
        return small_clusters

    grouped = df_inputs.groupby("Transaction ID")

    for txid, group in grouped:
        addresses = set(group["Input Address"].dropna().unique())

        if len(addresses) > 1:
            small_clusters.append(addresses)

    return small_clusters


# -----------------------------
# 5. Merge overlapping clusters
#    Example: {A,B} + {B,C} -> {A,B,C}
# -----------------------------
# If two clusters share at least one address, combine them into a bigger cluster
# This is because the addresses in the two clusters are very likely to have the same owner (not always true, will note exceptions)
def merge_overlapping_sets(list_of_sets):
    """Merge address clusters that overlap."""
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


# -----------------------------
# 6. Addresses that appear at least twice in my dataset
# -----------------------------
# My dataset is the two transactions of my seed address, plus the data in my transaction_inputs and transaction_outputs tables
# Want to look at addresses that apear at least twice because they are more likely to be part a network and not just one-offs
def get_repeat_addresses(df_inputs, df_outputs, min_appearances=2):
    """Find addresses that appear more than once in inputs or outputs."""
    input_counts = df_inputs["Input Address"].dropna().value_counts()
    output_counts = df_outputs["Output Address"].dropna().value_counts()

    repeated_inputs = set(input_counts[input_counts >= min_appearances].index)
    repeated_outputs = set(output_counts[output_counts >= min_appearances].index)

    return repeated_inputs.union(repeated_outputs)


# -----------------------------
# 7. Addresses that are in merged clusters
# -----------------------------
def get_cluster_addresses(merged_clusters, min_cluster_size=2):
    """Return addresses from merged clusters that meet the minimum size."""
    cluster_addresses = set()

    for cluster in merged_clusters:
        if len(cluster) >= min_cluster_size:
            cluster_addresses.update(cluster)

    return cluster_addresses


# -----------------------------
# 8. Final rule for addresses to expand
#    Current rule:
#    expand cluster addresses only
# -----------------------------
# Continue tracing addresses that are in the consolidated cluster
def choose_addresses_to_expand(df_inputs, df_outputs, merged_clusters, seed_address, min_appearances=2):
    """Choose candidate addresses for deeper follow-up tracing.

    This version uses cluster-only expansion to keep the investigation tightly
    linked to the multi-input heuristic.
    """
    repeat_addresses = get_repeat_addresses(
        df_inputs, df_outputs, min_appearances=min_appearances
    )
    cluster_addresses = get_cluster_addresses(merged_clusters)

    # currently using cluster-only expansion
    chosen_addresses = cluster_addresses

    # remove seed address if present
    chosen_addresses.discard(seed_address)

    return sorted(chosen_addresses)


# -----------------------------
# 9. Build cluster dataframe
#    One row per address in one merged cluster
# -----------------------------
# Build dataframe of final cluster
def build_clusters_dataframe(merged_clusters):
    """Convert merged clusters into a table for display."""
    cluster_rows = []

    for i, cluster in enumerate(merged_clusters, start=1):
        for addr in cluster:
            cluster_rows.append({
                "Cluster ID": i,
                "Address": addr,
                "Cluster Size": len(cluster)
            })

    df_clusters = pd.DataFrame(cluster_rows)

    if not df_clusters.empty:
        df_clusters = df_clusters.sort_values(
            by=["Cluster Size", "Cluster ID", "Address"],
            ascending=[False, True, True]
        ).reset_index(drop=True)

    return df_clusters


def build_transaction_flow_graph(df_inputs, df_outputs):
    """Build directed address → transaction → address graph data."""
    # Flow graph - shows movement

    # Each transaction is a bridge node
    # Bitcoin flows: input address → transaction → output address
    # This structure reflects how Bitcoin actually works:
    # Inputs fund a transaction
    # Outputs distribute that value

    # Blue dots = addresses
    # Grey dots = transactions
    # Arrows = flow of Bitcoin
    # Funds from many input addresses were combined into one transaction, then split into two output addresses

    # Create a directed graph
    # Directed = edges have direction (money flows from A → B)
    G = nx.DiGraph()

    # -----------------------------
    # ADD INPUT EDGES
    # -----------------------------
    # These represent: address → transaction
    # (i.e. address is PROVIDING funds to the transaction)
    for _, row in df_inputs.iterrows():
        if pd.notna(row["Input Address"]):
            G.add_edge(
                row["Input Address"],
                row["Transaction ID"],
                value=row["Input Value"],
                edge_type="input"
            )

    # -----------------------------
    # ADD OUTPUT EDGES
    # -----------------------------
    # These represent: transaction → address
    # (i.e. transaction sends BTC to this address)
    for _, row in df_outputs.iterrows():
        if pd.notna(row["Output Address"]):
            G.add_edge(
                row["Transaction ID"],
                row["Output Address"],
                value=row["Output Value"],
                edge_type="output"
            )

    return G


def draw_transaction_flow_graph(G, seed_address, traced_address=None, title="Bitcoin Transaction Flow Graph"):
    """Create a matplotlib figure for the transaction flow graph."""
    fig, ax = plt.subplots(figsize=(14, 8))

    pos = nx.spring_layout(G, k=0.5, seed=42)

    node_colours = []
    node_sizes = []

    for node in G.nodes():
        if node == seed_address:
            node_colours.append("#ef4444")
            node_sizes.append(800)
        elif traced_address is not None and node == traced_address:
            node_colours.append("#22c55e")
            node_sizes.append(800)
        elif is_bitcoin_address(node):
            node_colours.append("#93c5fd")
            node_sizes.append(420)
        else:
            node_colours.append("#d1d5db")
            node_sizes.append(260)

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_size=node_sizes,
        node_color=node_colours,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=14,
        alpha=0.85,
    )

    labels = {}
    for node in G.nodes():
        if node == seed_address:
            labels[node] = "Seed"
        elif traced_address is not None and node == traced_address:
            labels[node] = "Traced"
        elif not is_bitcoin_address(node) and G.degree(node) > 10:
            labels[node] = "Main Tx"

    nx.draw_networkx_labels(G, pos, labels=labels, font_size=9, ax=ax)

    legend_handles = [
        mpatches.Patch(color="#ef4444", label="Seed Address"),
        mpatches.Patch(color="#93c5fd", label="Address"),
        mpatches.Patch(color="#d1d5db", label="Transaction"),
    ]

    if traced_address is not None:
        legend_handles.insert(1, mpatches.Patch(color="#22c55e", label="Traced Address"))

    ax.legend(handles=legend_handles, loc="best")
    ax.set_title(title, pad=20)
    ax.axis("off")
    return fig


def build_cluster_graph(merged_clusters):
    """Build undirected graph connecting addresses in the same cluster."""
    # Shows the multi-input heuristic visually
    # Shows ownership structure

    # Nodes = addresses only
    # Lines = addresses that appeared together as inputs
    # Shows these addresses have been used together as inputs in transactions, suggesting they are controlled by the same entity

    # Create an undirected graph
    # Undirected = just showing relationships (not flow)
    cluster_graph = nx.Graph()

    # -----------------------------
    # ADD EDGES BETWEEN ADDRESSES
    # -----------------------------
    # If two addresses appear in the same input set,
    # we connect them → suggests same owner
    for cluster in merged_clusters:
        for address_a, address_b in combinations(list(cluster), 2):
            cluster_graph.add_edge(address_a, address_b)

    return cluster_graph


def draw_cluster_graph(cluster_graph):
    """Create a matplotlib figure showing inferred common-input clusters."""
    fig, ax = plt.subplots(figsize=(12, 8))

    if cluster_graph.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No multi-input clusters detected", ha="center", va="center")
        ax.axis("off")
        return fig

    pos = nx.spring_layout(cluster_graph, seed=42)

    nx.draw(
        cluster_graph,
        pos,
        ax=ax,
        with_labels=False,
        node_size=560,
        node_color="#a78bfa",
        edge_color="#6b7280",
        alpha=0.85,
    )

    ax.set_title("Multi-Input Address Cluster Graph", pad=20)
    ax.axis("off")
    return fig


def summarise_external_outputs(df_inputs, df_outputs, df_clusters):
    """Summarise where clustered addresses sent value outside the cluster."""
    if df_clusters.empty:
        return pd.DataFrame(columns=["Output Address", "Output Value", "BTC"])

    # Follow the money out of the cluster.
    # Step 1: get outgoing transactions from cluster.
    cluster_addresses = set(df_clusters["Address"])

    cluster_spending_txs = df_inputs[
        df_inputs["Input Address"].isin(cluster_addresses)
    ]["Transaction ID"].unique()

    # Step 2: get outputs of those transactions.
    cluster_outputs = df_outputs[
        df_outputs["Transaction ID"].isin(cluster_spending_txs)
    ]

    # Step 3: exclude internal cluster addresses.
    external_outputs = cluster_outputs[
        ~cluster_outputs["Output Address"].isin(cluster_addresses)
    ]

    # Step 4: rank where money went.
    summary = (
        external_outputs
        .groupby("Output Address")["Output Value"]
        .sum()
        .reset_index()
        .sort_values("Output Value", ascending=False)
        .reset_index(drop=True)
    )

    if not summary.empty:
        summary["BTC"] = (summary["Output Value"] / 100_000_000).round(4)

    return summary


def calculate_case_summary(all_txs, df_inputs, df_outputs, small_clusters, merged_clusters, addresses_to_expand):
    """Build a compact summary table for key case metrics."""
    largest_cluster_size = max((len(c) for c in merged_clusters), default=0)

    return {
        "transactions": len(all_txs),
        "input_rows": len(df_inputs),
        "output_rows": len(df_outputs),
        "small_clusters": len(small_clusters),
        "merged_clusters": len(merged_clusters),
        "largest_cluster_size": largest_cluster_size,
        "addresses_to_expand": len(addresses_to_expand),
    }


def analyse_case(seed_address):
    """Run the Locky clustering case pipeline."""
    all_txs = get_all_transactions(seed_address)
    df_inputs = build_transaction_inputs(all_txs)
    df_outputs = build_transaction_outputs(all_txs)

    small_clusters = build_input_clusters(df_inputs)
    merged_clusters = merge_overlapping_sets(small_clusters)

    addresses_to_expand = choose_addresses_to_expand(
        df_inputs,
        df_outputs,
        merged_clusters,
        seed_address,
        min_appearances=2,
    )

    df_clusters = build_clusters_dataframe(merged_clusters)
    external_summary = summarise_external_outputs(df_inputs, df_outputs, df_clusters)
    metrics = calculate_case_summary(
        all_txs,
        df_inputs,
        df_outputs,
        small_clusters,
        merged_clusters,
        addresses_to_expand,
    )

    return {
        "all_txs": all_txs,
        "df_inputs": df_inputs,
        "df_outputs": df_outputs,
        "small_clusters": small_clusters,
        "merged_clusters": merged_clusters,
        "addresses_to_expand": addresses_to_expand,
        "df_clusters": df_clusters,
        "external_summary": external_summary,
        "metrics": metrics,
    }


# -----------------------------
# App UI
# -----------------------------
st.title("🕵️ Locky Ransomware: Multi-Input Clustering Case")
st.caption("Investigator-style dashboard for demonstrating common-input address clustering.")

with st.sidebar:
    st.header("Case controls")
    seed_address = st.text_input("Seed address", DEFAULT_SEED_ADDRESS)
    target_address = st.text_input("1-hop traced address", DEFAULT_TARGET_ADDRESS)
    run_button = st.button("Run Locky analysis", type="primary")

    st.divider()
    st.markdown("**Investigation focus**")
    st.write("Common-input ownership heuristic")
    st.write("Seed transaction flow")
    st.write("Cluster graph")
    st.write("One-hop expansion")

if not run_button:
    st.info("Enter the case settings in the sidebar, then click **Run Locky analysis**.")
    st.stop()

try:
    with st.spinner("Fetching blockchain data and building clusters..."):
        results = analyse_case(seed_address)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()

metrics = results["metrics"]
df_inputs = results["df_inputs"]
df_outputs = results["df_outputs"]
df_clusters = results["df_clusters"]
external_summary = results["external_summary"]
merged_clusters = results["merged_clusters"]
addresses_to_expand = results["addresses_to_expand"]

st.markdown(
    f"""
    <div class="case-card">
    <h3>{CASE_NAME} case overview</h3>
    <p>This case uses a Locky-related seed address to demonstrate how multiple input
    addresses in one transaction can be grouped into a likely common-control cluster.</p>
    <p class="small-note">This is heuristic analysis. It supports investigation but does not prove real-world identity.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Transactions fetched", metrics["transactions"])
col2.metric("Input rows", metrics["input_rows"])
col3.metric("Largest cluster", metrics["largest_cluster_size"])
col4.metric("Expansion candidates", metrics["addresses_to_expand"])

col5, col6, col7 = st.columns(3)
col5.metric("Small clusters", metrics["small_clusters"])
col6.metric("Merged clusters", metrics["merged_clusters"])
cluster_received_btc = 0.0
if not df_clusters.empty:
    cluster_addresses = set(df_clusters["Address"])
    cluster_received_btc = df_outputs[
        df_outputs["Output Address"].isin(cluster_addresses)
    ]["Output Value"].sum() / 100_000_000
col7.metric("BTC received by cluster", f"{cluster_received_btc:.4f}")

tabs = st.tabs([
    "Case summary",
    "Input clusters",
    "Transaction flow",
    "One-hop expansion",
    "Method notes",
])

with tabs[0]:
    st.subheader("Case summary")
    st.write("The starting address has limited direct activity, but one transaction contains many unique input addresses. This makes it useful for showing the common-input ownership heuristic.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Seed address**")
        st.code(seed_address)
        st.markdown("**Addresses selected for expansion**")
        if addresses_to_expand:
            st.dataframe(pd.DataFrame({"Address": addresses_to_expand}), use_container_width=True)
        else:
            st.warning("No cluster expansion addresses were selected.")

    with right:
        st.markdown("**External outputs from clustered addresses**")
        if external_summary.empty:
            st.warning("No external outputs found from clustered addresses.")
        else:
            st.dataframe(external_summary.head(10), use_container_width=True)

    with st.expander("Raw input table"):
        st.dataframe(df_inputs, use_container_width=True)

    with st.expander("Raw output table"):
        st.dataframe(df_outputs, use_container_width=True)

with tabs[1]:
    st.subheader("Multi-input clusters")
    st.write("This table groups addresses that appear together as inputs, then merges overlapping groups into larger inferred clusters.")

    if df_clusters.empty:
        st.warning("No multi-input clusters detected.")
    else:
        st.dataframe(df_clusters, use_container_width=True)

    cluster_graph = build_cluster_graph(merged_clusters)
    st.pyplot(draw_cluster_graph(cluster_graph))

with tabs[2]:
    st.subheader("Transaction flow graph")
    st.write("This graph uses transaction nodes as bridges: input address → transaction → output address.")

    flow_graph = build_transaction_flow_graph(df_inputs, df_outputs)
    st.pyplot(draw_transaction_flow_graph(flow_graph, seed_address, title="Locky Seed Transaction Flow"))

with tabs[3]:
    st.subheader("One-hop expansion")
    st.write("This follows a selected external output address to inspect the next layer of activity separately from the original seed graph.")
    st.code(target_address)

    try:
        with st.spinner("Fetching one-hop target transactions..."):
            txs_2 = get_all_transactions(target_address)
            df_inputs_2 = build_transaction_inputs(txs_2)
            df_outputs_2 = build_transaction_outputs(txs_2)

        st.metric("Target transactions fetched", len(txs_2))

        with st.expander("Target input table"):
            st.dataframe(df_inputs_2, use_container_width=True)

        with st.expander("Target output table"):
            st.dataframe(df_outputs_2, use_container_width=True)

        hop_graph = build_transaction_flow_graph(df_inputs_2, df_outputs_2)
        st.pyplot(
            draw_transaction_flow_graph(
                hop_graph,
                seed_address,
                traced_address=target_address,
                title="1-Hop Expansion from Selected Output Address",
            )
        )
    except requests.exceptions.RequestException as exc:
        st.error(f"Could not fetch one-hop target data: {exc}")

with tabs[4]:
    st.subheader("Method notes")
    st.markdown(
        """
        **What the app is doing**

        - Fetches confirmed Bitcoin transactions for the Locky seed address.
        - Builds input and output tables from raw Blockstream API data.
        - Finds transactions with more than one unique input address.
        - Groups those input addresses into small clusters.
        - Merges overlapping clusters into larger inferred clusters.
        - Visualises both transaction flow and inferred common-input relationships.
        - Follows one selected external output address for a simple one-hop expansion.

        **Key assumption**

        The common-input ownership heuristic assumes that addresses used together
        as inputs in one transaction are likely controlled by the same entity.

        **Important limitation**

        This is not proof of real-world ownership. Collaborative transactions,
        exchange behaviour, wallet quirks and privacy tools can break or weaken
        the heuristic.
        """
    )
