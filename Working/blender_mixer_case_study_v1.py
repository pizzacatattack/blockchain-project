"""
Blender.io Mixer Case Study

This Streamlit app uses public blockchain data to show mixer-style transaction
structure using OFAC-listed Blender.io Bitcoin addresses.

Case logic:
1. Start with public Blender.io addresses listed by OFAC.
2. Select the address with the strongest visible activity from Blockstream.
3. Show address-level activity summary.
4. Select a representative transaction involving that address.
5. Visualise the transaction as a pooled flow: inputs -> transaction -> outputs.
6. Explain why mixer activity weakens simple ownership tracing.

The app is intentionally hardcoded for a case-study/demo setting.
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
CASE_NAME = "Blender.io Mixer Case Study"

# OFAC-listed Blender.io Bitcoin addresses.

BLENDER_ADDRESSES = [
    "3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3",
    "3Q5dGfLKkWqWSwYtbMUyc8xGjN5LrRviK4",
    "3EPqGUw2q89pwPZ1UF8FJspE2AyojSTjdu",
    "3LhnVMcBq4gsR7aDaRr9XmUo17CuYBV4FN",
    "3F6bbvS1krsc1qR8FsbTDfYQyvkMm3QvmR",
    "3JHMz3mTna1gVCZSPp8NgRFiY7phkv5mA8",
    "32DaxSzUhLBHY2WGSWQYiBSHnRsfQZrrRp",
    "3MTRvM5QrYZHKo8gh5qKcrPK3RLjxcDCZE",
    "34pFGsSYbWEritXncW9unZtQQE9dKSvKku",
    "38ncxqt932N9CcfNfYuHGZgCyR85hDkWBW",
    "3MD3riFB6U8PykypF6qkvSj8R2SGdUDPn3",
    "3JUwAS7seL3fh5hxWh9fu3HCiEzjuQLTfg",
    "3EUjqe9UpmyXCFd6jeu69hoTzndMRfxw9M",
    "3QEjBiPzw6WZUL4MYMmMU6DY1Y25aVbpQu",
    "3N3YSDvp4cbhEgNGabQxTN39kEzJmwG8Ah",
    "3J19qffPT6mxQUcV6k5yVURGZtdhpdGr4y",
    "33KKjn4exdBJQkTtdWxqpdVsWxrw3LareG",
    "3GSXNXzyCDoQ1Rhsc7F1jjjFe7DGcHHdcM",
    "3QJyT8nThEQakbfqgX86YjCK1Sp9hfNCUW",
    "35hh9dg3wSvUJz9vFk1FsezLE5Fx3Hudk2",
    "3NDzzVxiLBUs1WPvVGRfCYDTAD2Ua2PvW4",
    "3DCCgmyKozcZkFBzYb1A2x8abZCpAUTPPk",
    "3MvQ4gThF4mmuo49p4dBNchcmFHBRZnYfx",
    "3FBgeJdhiBe22UoSpp51Vd8dPHVa2A4wZX",
    "3HQDRyzwm82MFmLWtmyikDM9JQEtVT6vAp",
    "31t4nEpcwyQJT1VuXdAoQZTT5givRDPsNP",
    "39AALn7eTjdPzLb99hHhD6F7J8QWB3R2Rd",
    "3LDbNuDkKmLae5r3a5icPA5CQg2Y8F7ogW",
    "3JLyyLbwciWAC6re87D7mRknXakR4YbnUd",
    "3ANWhUnHujdwbw2jEuGSRH6bvFsD9BqEy9",
    "32fbAZMTaQxNd2fAue1PgsiPgWfcsHBQQt",
    "3HupEUfKmMhvhXqf8TMoPAyqDcRC1kpe65",
    "34kEYgpijvCmjvahRXXQEnBH76UGJVx2wg",
    "3GYbbYkvqvjF5oYhaKCgQYCvcVE1JENk6J",
    "3BazbaTP8ELJUEfPBV9z5HXEdgBziV9p7W",
    "3GMfGEDYMTq9G8dEHet1zLtUFJwYwSNa3Y",
    "38LjCapRrJEW7w2zwbyS15P9D9UGPjWS44",
    "36XqYWGvUQwBrYLRVuegN4pJJJSPWL1WEu",
    "37g6WgqedzZx6nx51tYgssNG8Hnknyj5nL",
    "3QAdoc1rDCt8dii1GVPJXvvK6CEJLzCRZw",
    "32PsiT8itBrEF84ebdaF82yBUEcz5Wc6uY",
    "3B4G1M8eF3cThbeMwhEWkKzczw9QoNTGak",
    "34ETiHfQWEYFCCaXmEeQWVmhFH5vz2JMvd",
    "3PyzSbFj3hbQQjTzDzyLSgvFVDjB7yw4Cj",
    "15PggTG7YhJKiE6B16vkKzA1YDTZipXEX4",
]

REQUEST_TIMEOUT_SECONDS = 20
SATOSHIS_PER_BTC = 100_000_000
MAX_ADDRESS_PAGES = 3
MAX_GRAPH_INPUTS = 8
MAX_GRAPH_OUTPUTS = 10

TREASURY_PRESS_RELEASE_URL = "https://home.treasury.gov/news/press-releases/jy0768"
OFAC_BLENDER_URL = "https://sanctionssearch.ofac.treas.gov/Details.aspx?id=37070"
BLOCKSTREAM_URL = "https://blockstream.info"


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


@st.cache_data(show_spinner=False)
def get_outspend(txid: str, vout_index: int) -> Dict[str, Any]:
    """Check whether a specific output has been spent."""
    url = f"{BLOCKSTREAM_URL}/api/tx/{txid}/outspend/{vout_index}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def get_transaction(txid: str) -> Dict[str, Any]:
    """Fetch a full transaction by txid."""
    url = f"{BLOCKSTREAM_URL}/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def find_blender_output(tx: Dict[str, Any]) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Find Blender-listed output in representative transaction."""
    for index, vout in enumerate(tx.get("vout", [])):
        address = safe_address(vout)
        if address in BLENDER_ADDRESSES:
            return index, vout
    return None


def get_input_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        address = prevout.get("scriptpubkey_address")
        value_btc = sats_to_btc(prevout.get("value", 0))
        rows.append(
            {
                "Input Index": index,
                "Input Address": address,
                "Input BTC": value_btc,
                "Is Blender Address": address in BLENDER_ADDRESSES,
            }
        )
    return rows


def get_output_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vout in enumerate(tx.get("vout", [])):
        address = safe_address(vout)
        value_btc = sats_to_btc(vout.get("value", 0))
        rows.append(
            {
                "Output Index": index,
                "Output Address": address,
                "Output BTC": value_btc,
                "Is Blender Address": address in BLENDER_ADDRESSES,
            }
        )
    return rows


def tx_involves_blender(tx: Dict[str, Any]) -> bool:
    for row in get_input_rows(tx):
        if row["Input Address"] in BLENDER_ADDRESSES:
            return True
    for row in get_output_rows(tx):
        if row["Output Address"] in BLENDER_ADDRESSES:
            return True
    return False


def score_representative_transaction(tx: Dict[str, Any]) -> float:
    """Score transactions for visually compelling mixer behaviour."""
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    input_count = len(inputs)
    output_count = len(outputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)

    blender_in_inputs = any(row["Is Blender Address"] for row in inputs)
    blender_in_outputs = any(row["Is Blender Address"] for row in outputs)

    score = 0

    # Inputs matter, but outputs matter more for mixer visuals
    score += input_count * 3

    # Strongly reward many outputs
    score += output_count * 15

    # Small reward for meaningful transaction size
    score += min(total_output_btc, 100) * 0.2

    # Prefer transactions directly involving Blender addresses
    if blender_in_inputs:
        score += 40

    if blender_in_outputs:
        score += 20

    # Penalise boring consolidation / batching transactions
    if output_count <= 2:
        score -= 150

    elif output_count <= 4:
        score -= 75

    # Bonus for transactions that actually look like mixing
    if input_count >= 4 and output_count >= 6:
        score += 100

    if input_count >= 6 and output_count >= 10:
        score += 150

    return score


def choose_case_address() -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    best_address = None
    best_info = None
    best_txs: List[Dict[str, Any]] = []
    best_score = -1

    for address in BLENDER_ADDRESSES:
        try:
            info = get_address_info(address)
            txs = get_address_transactions(address, max_pages=MAX_ADDRESS_PAGES)

            chain_stats = info.get("chain_stats", {})
            funded_btc = sats_to_btc(chain_stats.get("funded_txo_sum", 0))
            spent_btc = sats_to_btc(chain_stats.get("spent_txo_sum", 0))
            tx_count = chain_stats.get("tx_count", 0)

            candidate_score = tx_count + (funded_btc * 0.2) + (spent_btc * 0.2)

            if candidate_score > best_score and txs:
                best_score = candidate_score
                best_address = address
                best_info = info
                best_txs = txs

        except requests.exceptions.RequestException:
            continue

    if best_address is None or best_info is None:
        raise ValueError("Could not fetch usable Blender.io address data from Blockstream.")

    return best_address, best_info, best_txs


def choose_representative_transaction(txs: List[Dict[str, Any]]) -> Dict[str, Any]:
    relevant = [tx for tx in txs if tx_involves_blender(tx)]
    pool = relevant if relevant else txs

    if not pool:
        raise ValueError("No transactions found for representative mixer graph.")

    return max(pool, key=score_representative_transaction)


def build_address_summary(address: str, info: Dict[str, Any]) -> pd.DataFrame:
    chain_stats = info.get("chain_stats", {})
    mempool_stats = info.get("mempool_stats", {})

    funded_btc = sats_to_btc(chain_stats.get("funded_txo_sum", 0))
    spent_btc = sats_to_btc(chain_stats.get("spent_txo_sum", 0))
    balance_btc = funded_btc - spent_btc

    rows = [
        {"Metric": "Selected Blender.io address", "Value": address},
        {"Metric": "Confirmed transaction count", "Value": chain_stats.get("tx_count", 0)},
        {"Metric": "Confirmed BTC received", "Value": btc(funded_btc)},
        {"Metric": "Confirmed BTC spent", "Value": btc(spent_btc)},
        {"Metric": "Current confirmed balance", "Value": btc(balance_btc)},
        {"Metric": "Mempool transaction count", "Value": mempool_stats.get("tx_count", 0)},
    ]
    return pd.DataFrame(rows)


def build_transaction_summary(tx: Dict[str, Any]) -> pd.DataFrame:
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    total_input_btc = sum(row["Input BTC"] for row in inputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)
    fee_btc = sats_to_btc(tx.get("fee", 0))

    rows = [
        {"Metric": "Representative transaction", "Value": tx.get("txid")},
        {"Metric": "Date", "Value": format_date(tx.get("status", {}).get("block_time"))},
        {"Metric": "Input count", "Value": len(inputs)},
        {"Metric": "Output count", "Value": len(outputs)},
        {"Metric": "Total input BTC", "Value": btc(total_input_btc)},
        {"Metric": "Total output BTC", "Value": btc(total_output_btc)},
        {"Metric": "Transaction fee", "Value": btc(fee_btc)},
    ]
    return pd.DataFrame(rows)


def draw_mixer_transaction_graph(tx: Dict[str, Any], selected_address: str) -> plt.Figure:
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    inputs_sorted = sorted(inputs, key=lambda row: row["Input BTC"], reverse=True)
    outputs_sorted = sorted(outputs, key=lambda row: row["Output BTC"], reverse=True)

    shown_inputs = inputs_sorted[:MAX_GRAPH_INPUTS]
    shown_outputs = outputs_sorted[:MAX_GRAPH_OUTPUTS]

    other_input_btc = sum(row["Input BTC"] for row in inputs_sorted[MAX_GRAPH_INPUTS:])
    other_output_btc = sum(row["Output BTC"] for row in outputs_sorted[MAX_GRAPH_OUTPUTS:])

    G = nx.DiGraph()
    tx_node = "Mixer transaction"

    pos = {}
    labels = {}
    node_colours = []
    node_sizes = []

    input_nodes = []
    for i, row in enumerate(shown_inputs):
        node = f"Input {i}"
        input_nodes.append((node, row))
        G.add_edge(node, tx_node)

    if other_input_btc > 0:
        node = "Other inputs"
        input_nodes.append((node, {"Input BTC": other_input_btc, "Input Address": "Other inputs", "Is Blender Address": False}))
        G.add_edge(node, tx_node)

    for i, (node, row) in enumerate(input_nodes):
        y = (len(input_nodes) - 1) / 2 - i
        pos[node] = (-3.6, y * 0.9)

        value = row.get("Input BTC", 0)
        address = row.get("Input Address")

        if address == selected_address or row.get("Is Blender Address"):
            labels[node] = f"Blender\n{value:.2f} BTC"
        elif node == "Other inputs":
            labels[node] = f"Other inputs\n{value:.2f} BTC"
        else:
            labels[node] = f"{value:.2f} BTC"

    pos[tx_node] = (0, 0)
    labels[tx_node] = "TX"

    output_nodes = []
    for i, row in enumerate(shown_outputs):
        node = f"Output {i}"
        output_nodes.append((node, row))
        G.add_edge(tx_node, node)

    if other_output_btc > 0:
        node = "Other outputs"
        output_nodes.append((node, {"Output BTC": other_output_btc, "Output Address": "Other outputs", "Is Blender Address": False}))
        G.add_edge(tx_node, node)

    for i, (node, row) in enumerate(output_nodes):
        y = (len(output_nodes) - 1) / 2 - i
        pos[node] = (3.6, y * 0.72)

        value = row.get("Output BTC", 0)
        address = row.get("Output Address")

        if address == selected_address or row.get("Is Blender Address"):
            labels[node] = f"Blender\n{value:.2f} BTC"
        elif node == "Other outputs":
            labels[node] = f"Other outputs\n{value:.2f} BTC"
        else:
            labels[node] = f"{value:.2f} BTC"

    for node in G.nodes():
        label = labels.get(node, "")
        if node == tx_node:
            node_colours.append("#9ca3af")
            node_sizes.append(1900)
        elif label.startswith("Blender"):
            node_colours.append("#f97316")
            node_sizes.append(2100)
        elif node.startswith("Input") or node == "Other inputs":
            node_colours.append("#93c5fd")
            node_sizes.append(1700)
        else:
            node_colours.append("#22c55e")
            node_sizes.append(1700)

    max_y = max(len(input_nodes), len(output_nodes)) * 0.5
    fig_height = max(6.5, max_y + 2.5)
    fig, ax = plt.subplots(figsize=(14, fig_height))

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
        arrowsize=16,
        width=1.35,
        alpha=0.95,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=7,
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color="#f97316", label="OFAC-listed Blender.io address"),
        mpatches.Patch(color="#93c5fd", label="Input side"),
        mpatches.Patch(color="#9ca3af", label="Transaction"),
        mpatches.Patch(color="#22c55e", label="Output side"),
    ]

    ax.legend(handles=legend_handles, loc="upper right")
    ax.set_title("Mixer transaction structure: pooled inputs and redistributed outputs", pad=18, fontsize=13)

    ax.set_xlim(-4.5, 4.5)
    ax.axis("off")
    fig.tight_layout()
    return fig










def draw_blender_followup_graph(spend_tx: Dict[str, Any], blender_value: float) -> plt.Figure:
    """Show what happens after Blender receives BTC."""
    outputs = get_output_rows(spend_tx)
    outputs_sorted = sorted(outputs, key=lambda row: row["Output BTC"], reverse=True)

    shown_outputs = outputs_sorted[:12]
    other_output_btc = sum(row["Output BTC"] for row in outputs_sorted[12:])

    G = nx.DiGraph()

    source_node = "Blender deposit"
    tx_node = "Redistribution"

    G.add_edge(source_node, tx_node)

    pos = {
        source_node: (-3, 0),
        tx_node: (0, 0),
    }

    labels = {
        source_node: f"Blender\n{blender_value:.2f} BTC",
        tx_node: "Spend TX",
    }

    for i, row in enumerate(shown_outputs):
        node = f"Output {i}"
        y = ((len(shown_outputs) - 1) / 2) - i

        G.add_edge(tx_node, node)
        pos[node] = (3, y * 0.6)
        labels[node] = f"{row['Output BTC']:.2f} BTC"

    if other_output_btc > 0:
        node = "Other outputs"
        G.add_edge(tx_node, node)
        pos[node] = (3, -4.5)
        labels[node] = f"Other\n{other_output_btc:.2f} BTC"

    colours = []
    sizes = []

    for node in G.nodes():
        if node == source_node:
            colours.append("#f97316")
            sizes.append(2200)
        elif node == tx_node:
            colours.append("#9ca3af")
            sizes.append(1800)
        else:
            colours.append("#22c55e")
            sizes.append(1400)

    fig, ax = plt.subplots(figsize=(14, 8))

    nx.draw(
        G,
        pos,
        ax=ax,
        with_labels=False,
        node_color=colours,
        node_size=sizes,
        edge_color="#6b7280",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
        width=1.4,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8,
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color="#f97316", label="Blender address"),
        mpatches.Patch(color="#9ca3af", label="Spending transaction"),
        mpatches.Patch(color="#22c55e", label="Redistributed outputs"),
    ]

    ax.legend(handles=legend_handles, loc="upper right")
    ax.set_title("What the Blender-listed address does next", fontsize=13)
    ax.axis("off")
    fig.tight_layout()

    return fig










# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A Bitcoin tracing case study showing how mixer transactions weaken direct ownership tracing.")

st.markdown(
    """
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
            Blender.io was a Bitcoin mixer sanctioned by OFAC. Treasury stated that Blender.io was used to
            support malicious cyber activity and to launder stolen virtual currency. The OFAC listing includes
            Bitcoin addresses associated with the service.
        </p>
        <p>
            This case starts from OFAC-listed Blender.io addresses and uses Blockstream data to show mixer-style
            transaction structure. The point is not to identify a single end recipient. The point is to show why
            direct tracing becomes less reliable when funds pass through a mixer.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.header("How mixer tracing differs from normal tracing")
st.markdown(
    """
    <div class="case-card">
        <p>
            In a normal tracing case, an analyst may try to follow value from one address to the next.
            A mixer changes that problem. Funds from different users can be pooled together and then sent
            back out through new outputs. This makes it harder to prove that one specific input maps to one
            specific output.
        </p>
        <p>
            This also weakens simple ownership assumptions. A transaction with many inputs does not always mean
            all inputs belong to one person or group, especially when the transaction is part of a mixing service.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading Blender.io address and transaction data from Blockstream..."):
        selected_address, address_info, address_txs = choose_case_address()
        representative_tx = choose_representative_transaction(address_txs)

        blender_followup_tx = None
        blender_output_value = None

        blender_output = find_blender_output(representative_tx)

        if blender_output:
            output_index, vout = blender_output
            blender_output_value = sats_to_btc(vout["value"])

            outspend = get_outspend(representative_tx["txid"], output_index)

            if outspend.get("spent"):
                blender_followup_tx = get_transaction(outspend["txid"])

except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()

except Exception as exc:
    st.error(f"Case loading failed: {exc}")
    st.stop()

chain_stats = address_info.get("chain_stats", {})
funded_btc = sats_to_btc(chain_stats.get("funded_txo_sum", 0))
spent_btc = sats_to_btc(chain_stats.get("spent_txo_sum", 0))
balance_btc = funded_btc - spent_btc

tx_inputs = get_input_rows(representative_tx)
tx_outputs = get_output_rows(representative_tx)
total_output_btc = sum(row["Output BTC"] for row in tx_outputs)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Selected address txs", chain_stats.get("tx_count", 0))
col2.metric("BTC received", f"{funded_btc:.4f}")
col3.metric("BTC spent", f"{spent_btc:.4f}")
col4.metric("Representative inputs", len(tx_inputs))
col5.metric("Representative outputs", len(tx_outputs))

st.markdown(
    f"""
    <div class="case-card">
        <h3>What the case shows</h3>
        <p>
            The selected Blender.io address is <code>{selected_address}</code>. It appears in a public OFAC listing
            for Blender.io. The address has confirmed blockchain activity visible through Blockstream.
        </p>
        <p>
            The representative transaction selected by the app contains <strong>{len(tx_inputs)} inputs</strong>
            and <strong>{len(tx_outputs)} outputs</strong>, moving approximately
            <strong>{total_output_btc:.4f} BTC</strong> across the output side. This structure is useful for showing
            why mixer transactions interrupt simple one-to-one tracing.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Mixer transaction graph")
st.write(
    "The graph shows the selected Blender.io address in orange. Inputs are pooled through a transaction, "
    "then value leaves through multiple outputs. This is the point where direct input-to-output ownership "
    "mapping becomes unreliable."
)
st.pyplot(draw_mixer_transaction_graph(representative_tx, selected_address), use_container_width=True)

if blender_followup_tx:
    st.subheader("2. What the Blender address does next")
    st.write(
        "This graph follows the Blender-listed address after it receives BTC. "
        "If the funds are redistributed into many outputs, this strengthens the mixer behaviour pattern."
    )

    st.pyplot(
        draw_blender_followup_graph(blender_followup_tx, blender_output_value),
        use_container_width=True
    )

st.subheader("2. Representative transaction summary")
st.dataframe(build_transaction_summary(representative_tx), use_container_width=True, hide_index=True)

st.subheader("3. Address summary")
st.dataframe(build_address_summary(selected_address, address_info), use_container_width=True, hide_index=True)

with st.expander("Show representative transaction inputs and outputs"):
    st.markdown("**Inputs**")
    st.dataframe(pd.DataFrame(tx_inputs), use_container_width=True, hide_index=True)

    st.markdown("**Outputs**")
    st.dataframe(pd.DataFrame(tx_outputs), use_container_width=True, hide_index=True)

st.subheader("Interpretation note")
st.markdown(
    """
    <div class="case-card">
        <p>
            Blockchain data shows transaction movement, not real-world identity. In this case, the Blender.io
            connection comes from the public OFAC listing. The graph shows transaction structure, not a guaranteed
            match between any one input and any one output.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("References")
with st.expander("Show references and data sources"):
    st.markdown(
        f"""
        U.S. Department of the Treasury (2022) *U.S. Treasury Issues First-Ever Sanctions on a Virtual Currency Mixer*. Available at: {TREASURY_PRESS_RELEASE_URL}.

        Office of Foreign Assets Control (OFAC) (2022) *Sanctions List Search: Blender.io*. Available at: {OFAC_BLENDER_URL}.

        Blockstream (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/explorer-api.
        """
    )
