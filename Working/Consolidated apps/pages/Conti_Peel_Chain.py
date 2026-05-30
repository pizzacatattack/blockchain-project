"""
Peel-chain tracing case study

This Streamlit app follows a peel-chain path using transaction outputs (UTXOs),
not address-level output summaries.

Case logic:
1. Start with a seed address.
2. Find the largest outgoing output connected to that seed address.
3. Treat that output as the starting UTXO for the main flow.
4. Use Blockstream's outspend endpoint to find the transaction that spends it.
5. In the spending transaction, select the dominant continuing output.
6. Repeat this transaction-by-transaction.

This keeps the case aligned with peel-chain tracing: a large output is spent,
a smaller amount is separated, and the remaining value continues forward.
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
# CASE_NAME = "Conti Ransomware Peel-Chain Case Study"
# SEED_ADDRESS = "13XELohdTXGbgHpwRrNHMiuKrjA7a9wM2z"
# REQUEST_TIMEOUT_SECONDS = 20
# SATOSHIS_PER_BTC = 100_000_000
# DEFAULT_MAX_HOPS = 14
# DEFAULT_GRAPH_STEPS = 8
# MIN_CONTINUING_BTC = 0.001
# CANDIDATE_LIMIT = 10
# BLOCKSTREAM_ADDRESS_URL = f"https://blockstream.info/address/{SEED_ADDRESS}"


CASE_NAME = "Conti Ransomware Peel-Chain Case Study"
SEED_ADDRESS = "13XELohdTXGbgHpwRrNHMiuKrjA7a9wM2z"

REQUEST_TIMEOUT_SECONDS = 20
SATOSHIS_PER_BTC = 100_000_000

# Follow the chain until it naturally stops or becomes too small.
DEFAULT_MAX_HOPS = 100
MIN_CONTINUING_BTC = 0.001

# No artificial graph cap: show the full traced path.
DEFAULT_GRAPH_STEPS = DEFAULT_MAX_HOPS

# We have selected the Conti seed address, so we do not need broad candidate searching.
CANDIDATE_LIMIT = 1

BLOCKSTREAM_ADDRESS_URL = f"https://blockstream.info/address/{SEED_ADDRESS}"

CONTI_DATASET_URL = "https://github.com/cablej/conti-payments"
CONTI_PAPER_URL = "https://arxiv.org/abs/2304.11681"


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
def sats_to_btc(value: Optional[int]) -> float:
    """Convert satoshis to BTC."""
    if value is None:
        return 0.0
    return value / SATOSHIS_PER_BTC


def btc(value: float) -> str:
    """Format BTC values consistently."""
    return f"{value:.8f} BTC"


def short_txid(txid: str) -> str:
    """Shorten a transaction ID for graph labels."""
    if not txid:
        return "Unknown"
    return f"{txid[:8]}…{txid[-6:]}"


def format_date(timestamp: Optional[int]) -> str:
    """Format a UNIX timestamp as a readable date."""
    if not timestamp:
        return "Unconfirmed / unknown"
    return datetime.utcfromtimestamp(timestamp).strftime("%d %b %Y")


def safe_address(vout: Dict[str, Any]) -> Optional[str]:
    """Return an output address if Blockstream provides one."""
    return vout.get("scriptpubkey_address")


@st.cache_data(show_spinner=False)
def get_transaction(txid: str) -> Dict[str, Any]:
    """Fetch a transaction by transaction ID."""
    url = f"https://blockstream.info/api/tx/{txid}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def get_outspend(txid: str, vout_index: int) -> Dict[str, Any]:
    """Fetch spend information for a specific transaction output."""
    url = f"https://blockstream.info/api/tx/{txid}/outspend/{vout_index}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def get_address_transactions(address: str, max_pages: int = 4) -> List[Dict[str, Any]]:
    """Fetch confirmed transactions for an address with capped pagination."""
    all_txs: List[Dict[str, Any]] = []
    last_seen = None

    for _ in range(max_pages):
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
        time.sleep(0.35)

    return all_txs


def input_addresses(tx: Dict[str, Any]) -> List[str]:
    """Return input addresses from a transaction."""
    addresses = []
    for vin in tx.get("vin", []):
        prevout = vin.get("prevout") or {}
        address = prevout.get("scriptpubkey_address")
        if address:
            addresses.append(address)
    return addresses


def output_rows_for_tx(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return output rows for a transaction."""
    rows = []
    for index, vout in enumerate(tx.get("vout", [])):
        rows.append(
            {
                "Transaction ID": tx.get("txid"),
                "Date": format_date(tx.get("status", {}).get("block_time")),
                "Output Index": index,
                "Output Address": safe_address(vout),
                "Output BTC": sats_to_btc(vout.get("value")),
                "Output Sats": vout.get("value", 0),
            }
        )
    return rows


def find_starting_utxo(seed_address: str) -> Dict[str, Any]:
    """Find the largest output associated with transactions spending from the seed.

    The original address-level prototype surfaced the high-value lead by looking
    across the seed address transaction set. This UTXO version keeps that idea,
    but selects one concrete transaction output so the later tracing can follow
    the output that is actually spent.
    """
    txs = get_address_transactions(seed_address, max_pages=4)
    candidates: List[Dict[str, Any]] = []

    for tx in txs:
        txid = tx.get("txid")
        seed_is_input = seed_address in input_addresses(tx)

        # Prefer outputs from transactions where the seed address is an input.
        # If none are found, the fallback below still uses all outputs from the
        # seed transaction history.
        for row in output_rows_for_tx(tx):
            if row["Output Address"] == seed_address:
                continue
            if row["Output Address"] is None:
                continue
            row["Seed Was Input"] = seed_is_input
            row["Source Transaction ID"] = txid
            row["Source Date"] = row["Date"]
            candidates.append(row)

    if not candidates:
        raise ValueError("No candidate outputs found from the seed address transaction history.")

    preferred = [row for row in candidates if row["Seed Was Input"]]
    pool = preferred if preferred else candidates
    start = max(pool, key=lambda row: row["Output BTC"])

    return {
        "txid": start["Source Transaction ID"],
        "vout": int(start["Output Index"]),
        "address": start["Output Address"],
        "value_sats": int(start["Output Sats"]),
        "value_btc": float(start["Output BTC"]),
        "date": start["Source Date"],
    }


def choose_continuing_output(spending_tx: Dict[str, Any], previous_value_sats: int) -> Optional[Dict[str, Any]]:
    """Choose the output that continues the main peel-chain flow.

    For a case-study prototype, the continuing output is the largest output that
    is smaller than or equal to the value being spent. This mirrors the visible
    peel-chain pattern: the main balance continues, while the difference is
    separated into other outputs and fees.
    """
    outputs = []
    for index, vout in enumerate(spending_tx.get("vout", [])):
        value_sats = int(vout.get("value", 0))
        address = safe_address(vout)
        value_btc = sats_to_btc(value_sats)

        if address is None:
            continue
        if value_btc < MIN_CONTINUING_BTC:
            continue
        if value_sats > previous_value_sats:
            continue

        outputs.append(
            {
                "txid": spending_tx["txid"],
                "vout": index,
                "address": address,
                "value_sats": value_sats,
                "value_btc": value_btc,
            }
        )

    if not outputs:
        return None

    return max(outputs, key=lambda row: row["value_sats"])


def collect_starting_utxo_candidates(seed_address: str, candidate_limit: int = CANDIDATE_LIMIT) -> List[Dict[str, Any]]:
    """Collect high-value outputs from transactions linked to the seed address.

    For Conti, the seed address is treated as an entry point from public reporting.
    A single wallet may have several high-value outputs. Instead of automatically
    choosing the largest output, this function gives the app several candidate
    UTXOs to test and score.
    """
    txs = get_address_transactions(seed_address, max_pages=4)
    candidates: List[Dict[str, Any]] = []

    for tx in txs:
        txid = tx.get("txid")
        seed_is_input = seed_address in input_addresses(tx)

        for row in output_rows_for_tx(tx):
            if row["Output Address"] == seed_address:
                continue
            if row["Output Address"] is None:
                continue

            row["Seed Was Input"] = seed_is_input
            row["Source Transaction ID"] = txid
            row["Source Date"] = row["Date"]
            candidates.append(row)

    if not candidates:
        raise ValueError("No candidate outputs found from the seed address transaction history.")

    # Prefer outputs created by transactions where the seed address was an input.
    # If that produces no results, fall back to all transaction-history outputs.
    preferred = [row for row in candidates if row["Seed Was Input"]]
    pool = preferred if preferred else candidates

    # Test the largest candidates first. This keeps the app practical while still
    # avoiding the old mistake of blindly trusting only the single largest output.
    pool = sorted(pool, key=lambda row: row["Output BTC"], reverse=True)
    pool = pool[:candidate_limit]

    return [
        {
            "txid": row["Source Transaction ID"],
            "vout": int(row["Output Index"]),
            "address": row["Output Address"],
            "value_sats": int(row["Output Sats"]),
            "value_btc": float(row["Output BTC"]),
            "date": row["Source Date"],
        }
        for row in pool
    ]


def trace_from_starting_utxo(starting_utxo: Dict[str, Any], max_hops: int) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Trace a peel-chain path from one concrete starting UTXO."""
    logs: List[str] = []
    rows: List[Dict[str, Any]] = []
    separated_rows: List[Dict[str, Any]] = []

    current = dict(starting_utxo)
    logs.append(
        f"Starting UTXO tested: {btc(current['value_btc'])} at "
        f"{current['txid']}:{current['vout']}"
    )

    seen_utxos = set()

    for step in range(1, max_hops + 1):
        utxo_key = (current["txid"], current["vout"])
        if utxo_key in seen_utxos:
            logs.append("Repeated UTXO reached. Trace stopped.")
            break
        seen_utxos.add(utxo_key)

        outspend = get_outspend(current["txid"], current["vout"])
        spent = bool(outspend.get("spent"))

        row = {
            "Step": step,
            "UTXO": f"{current['txid']}:{current['vout']}",
            "Date Created": current.get("date"),
            "Continuing Address": current.get("address"),
            "Continuing BTC": current.get("value_btc"),
            "Spending Transaction": None,
            "Next UTXO": None,
            "Next Continuing BTC": None,
            "Value Peeled Off": None,
            "Other Outputs BTC": None,
            "Transaction Fee BTC": None,
        }

        if not spent:
            logs.append(f"Step {step}: output is unspent. Trace stopped.")
            rows.append(row)
            break

        spending_txid = outspend.get("txid")
        spending_tx = get_transaction(spending_txid)
        fee_btc = sats_to_btc(spending_tx.get("fee", 0))
        next_output = choose_continuing_output(spending_tx, current["value_sats"])

        if next_output is None:
            row["Spending Transaction"] = spending_txid
            rows.append(row)
            logs.append(f"Step {step}: no continuing output found. Trace stopped.")
            break

        separated_sats = max(current["value_sats"] - next_output["value_sats"], 0)
        separated_btc = sats_to_btc(separated_sats)
        other_outputs_btc = max(separated_btc - fee_btc, 0)

        row.update(
            {
                "Spending Transaction": spending_txid,
                "Next UTXO": f"{next_output['txid']}:{next_output['vout']}",
                "Next Continuing BTC": next_output["value_btc"],
                "Value Peeled Off": separated_btc,
                "Other Outputs BTC": other_outputs_btc,
                "Transaction Fee BTC": fee_btc,
            }
        )
        rows.append(row)

        for index, vout in enumerate(spending_tx.get("vout", [])):
            if index == next_output["vout"]:
                continue
            value_btc = sats_to_btc(vout.get("value", 0))
            if value_btc <= 0:
                continue
            separated_rows.append(
                {
                    "Step": step,
                    "Spending Transaction": spending_txid,
                    "Output Index": index,
                    "Output Address": safe_address(vout),
                    "BTC": value_btc,
                }
            )

        logs.append(
            f"Step {step}: {btc(current['value_btc'])} spent; "
            f"{btc(next_output['value_btc'])} continues; "
            f"{btc(separated_btc)} peeled off including fee."
        )

        current = {
            "txid": next_output["txid"],
            "vout": next_output["vout"],
            "address": next_output["address"],
            "value_sats": next_output["value_sats"],
            "value_btc": next_output["value_btc"],
            "date": format_date(spending_tx.get("status", {}).get("block_time")),
        }

        time.sleep(0.2)

    return pd.DataFrame(rows), pd.DataFrame(separated_rows), logs


def score_trace(peel_df: pd.DataFrame) -> float:
    """Score a candidate path for use as a case-study peel chain.

    The score rewards:
    - a large starting balance
    - several successful hops
    - visible depletion of the continuing flow
    - meaningful peeled-off value

    This helps the Conti case choose the most compelling path automatically.
    """
    if peel_df.empty:
        return -1

    valid = peel_df.dropna(subset=["Value Peeled Off", "Next Continuing BTC"])
    if valid.empty:
        return -1

    start_btc = float(peel_df.iloc[0]["Continuing BTC"])
    final_btc = float(valid.iloc[-1]["Next Continuing BTC"])
    total_peeled = float(valid["Value Peeled Off"].sum())
    hop_count = len(valid)
    depletion = max(start_btc - final_btc, 0)

    # Reject paths that barely move. They are not useful for this case study.
    if hop_count < 2:
        return -1

    return (start_btc * 0.4) + (depletion * 2.5) + (total_peeled * 1.5) + (hop_count * 10)


def trace_peel_chain_utxos(seed_address: str, max_hops: int) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Choose the strongest Conti-linked starting UTXO, then trace it forward."""
    candidates = collect_starting_utxo_candidates(seed_address, candidate_limit=CANDIDATE_LIMIT)

    best_score = -1
    best_result: Optional[Tuple[pd.DataFrame, pd.DataFrame, List[str]]] = None
    triage_logs: List[str] = []

    for candidate in candidates:
        try:
            peel_df, separated_df, logs = trace_from_starting_utxo(candidate, max_hops=max_hops)
            score = score_trace(peel_df)
            triage_logs.append(
                f"Candidate {short_txid(candidate['txid'])}:{candidate['vout']} "
                f"started at {candidate['value_btc']:.4f} BTC; score {score:.2f}."
            )

            if score > best_score:
                best_score = score
                best_result = (peel_df, separated_df, logs)

        except requests.exceptions.RequestException as exc:
            triage_logs.append(
                f"Candidate {short_txid(candidate['txid'])}:{candidate['vout']} skipped due to API error: {exc}"
            )
        except Exception as exc:
            triage_logs.append(
                f"Candidate {short_txid(candidate['txid'])}:{candidate['vout']} skipped: {exc}"
            )

    if best_result is None:
        raise ValueError("No usable Conti-linked peel-chain path was found from the tested outputs.")

    peel_df, separated_df, logs = best_result
    logs = ["Conti candidate triage:"] + triage_logs + ["Selected path:"] + logs
    return peel_df, separated_df, logs

def build_summary_rows(peel_df: pd.DataFrame) -> pd.DataFrame:
    """Build a concise summary table for the case."""
    if peel_df.empty:
        return pd.DataFrame()

    first = peel_df.iloc[0]
    valid = peel_df.dropna(subset=["Value Peeled Off"])
    last = valid.iloc[-1] if not valid.empty else peel_df.iloc[-1]

    rows = [
        {
            "Point": "Starting flow",
            "Finding": "The traced path begins from a high-value transaction output.",
            "BTC": btc(float(first["Continuing BTC"])),
        },
        {
            "Point": "Displayed hops",
            "Finding": "The app follows the continuing output transaction-by-transaction.",
            "BTC": str(len(valid)),
        },
        {
            "Point": "Total value separated",
            "Finding": "This is the total difference between the continuing balance at each displayed hop.",
            "BTC": btc(float(valid["Value Peeled Off"].sum())) if not valid.empty else "0 BTC",
        },
        {
            "Point": "Final displayed balance",
            "Finding": "This is the continuing balance at the end of the displayed path.",
            "BTC": btc(float(last["Next Continuing BTC"])) if pd.notna(last.get("Next Continuing BTC")) else btc(float(last["Continuing BTC"])),
        },
    ]
    return pd.DataFrame(rows)


def draw_peel_graph(peel_df: pd.DataFrame, graph_steps: int) -> plt.Figure:
    """Draw a clean peel-chain graph with minimal labels."""
    graph_df = peel_df.copy()
    G = nx.DiGraph()
    pos = {}
    labels = {}
    node_colours = []
    node_sizes = []

    # Main continuing path across the top.
    for i, row in graph_df.iterrows():
        step = int(row["Step"])
        main_node = f"Step {step}"
        pos[main_node] = (i * 3.4, 0.9)
        labels[main_node] = f"{row['Continuing BTC']:.1f} BTC"
        G.add_node(main_node)

        if step == 1:
            node_colours.append("#f97316")
            node_sizes.append(1800)
        else:
            node_colours.append("#93c5fd")
            node_sizes.append(1650)

    # Simple arrows between continuing balances. No edge labels because the next node
    # already shows the continuing BTC amount.
    for i in range(len(graph_df) - 1):
        src = f"Step {int(graph_df.iloc[i]['Step'])}"
        dst = f"Step {int(graph_df.iloc[i + 1]['Step'])}"
        G.add_edge(src, dst)

    # Peeled values beneath the main path.
    for i, row in graph_df.iterrows():
        peeled_value = row.get("Value Peeled Off")
        if pd.notna(peeled_value) and peeled_value > 0:
            step = int(row["Step"])
            peel_node = f"Peel {step}"
            main_node = f"Step {step}"
            pos[peel_node] = (i * 3.4, -0.75)
            labels[peel_node] = f"{peeled_value:.1f} BTC"
            G.add_node(peel_node)
            G.add_edge(main_node, peel_node)
            node_colours.append("#fca5a5")
            node_sizes.append(1250)

    width = max(13, len(graph_df) * 2.2)
    fig, ax = plt.subplots(figsize=(width, 5.8))
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
        width=1.5,
        alpha=0.95,
    )
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, ax=ax)

    legend_handles = [
        mpatches.Patch(color="#f97316", label="Starting balance"),
        mpatches.Patch(color="#93c5fd", label="Continuing balance"),
        mpatches.Patch(color="#fca5a5", label="Peeled value"),
    ]
    ax.legend(handles=legend_handles, loc="lower right")
    ax.set_title("Conti peel-chain tracing path", pad=18)
    ax.axis("off")
    fig.tight_layout()
    return fig




def get_consolidation_details(peel_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Return details for the transaction where the traced path stops by consolidation.

    The final row in this case has a spending transaction but no smaller continuing
    output. That usually means the traced UTXO was merged with other inputs rather
    than peeled again.
    """
    if peel_df.empty:
        return None

    last = peel_df.iloc[-1]
    spending_txid = last.get("Spending Transaction")

    if pd.isna(spending_txid) or spending_txid is None:
        return None

    traced_btc = float(last.get("Continuing BTC", 0))
    tx = get_transaction(str(spending_txid))

    input_rows = []
    total_input_btc = 0.0
    for i, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        value_btc = sats_to_btc(prevout.get("value", 0))
        total_input_btc += value_btc
        input_rows.append(
            {
                "Input Index": i,
                "Input Address": prevout.get("scriptpubkey_address"),
                "Input BTC": value_btc,
                "Role": "Traced peel-chain output" if abs(value_btc - traced_btc) < 0.0001 else "Other consolidation input",
            }
        )

    output_rows = []
    total_output_btc = 0.0
    for i, vout in enumerate(tx.get("vout", [])):
        value_btc = sats_to_btc(vout.get("value", 0))
        total_output_btc += value_btc
        output_rows.append(
            {
                "Output Index": i,
                "Output Address": safe_address(vout),
                "Output BTC": value_btc,
            }
        )

    return {
        "txid": str(spending_txid),
        "traced_btc": traced_btc,
        "input_count": len(input_rows),
        "output_count": len(output_rows),
        "total_input_btc": total_input_btc,
        "total_output_btc": total_output_btc,
        "fee_btc": sats_to_btc(tx.get("fee", 0)),
        "inputs": pd.DataFrame(input_rows),
        "outputs": pd.DataFrame(output_rows),
    }

def draw_consolidation_graph(final_spending_txid: str, traced_input_value: float) -> plt.Figure:
    """Draw the consolidation transaction where the final traced peel-chain output is merged."""
    tx = get_transaction(final_spending_txid)

    G = nx.DiGraph()
    tx_node = "TX"

    pos = {}
    labels = {}
    node_colours = []
    node_sizes = []

    # Collect inputs
    input_nodes = []
    for i, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        value_btc = sats_to_btc(prevout.get("value", 0))

        input_node = f"Input {i}"
        input_nodes.append((input_node, value_btc))
        G.add_edge(input_node, tx_node)

    # Put traced input first
    input_nodes = sorted(
        input_nodes,
        key=lambda item: 0 if abs(item[1] - traced_input_value) < 0.0001 else 1
    )

    # Position inputs vertically
    for i, (node, value_btc) in enumerate(input_nodes):
        y = (len(input_nodes) - 1) / 2 - i
        pos[node] = (-2.8, y * 1.2)

        labels[node] = f"{value_btc:.1f}\nBTC"

    # Transaction node
    pos[tx_node] = (0, 0)
    labels[tx_node] = "TX"

    # Outputs
    for i, vout in enumerate(tx.get("vout", [])):
        value_btc = sats_to_btc(vout.get("value", 0))
        output_node = f"Output {i}"
        G.add_edge(tx_node, output_node)

        pos[output_node] = (2.8, 0)
        labels[output_node] = f"{value_btc:.1f}\nBTC"

    # Styling
    for node in G.nodes():
        if node == tx_node:
            node_colours.append("#9ca3af")   # grey
            node_sizes.append(1800)

        elif node.startswith("Input"):
            value = None
            for n, v in input_nodes:
                if n == node:
                    value = v
                    break

            if value is not None and abs(value - traced_input_value) < 0.0001:
                node_colours.append("#f97316")   # orange traced input
                node_sizes.append(2300)
            else:
                node_colours.append("#93c5fd")   # blue other inputs
                node_sizes.append(2100)

        else:
            node_colours.append("#22c55e")   # green output
            node_sizes.append(2400)

    fig, ax = plt.subplots(figsize=(11, 6))

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
        arrowsize=18,
        width=1.8,
        alpha=0.95,
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=9,
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color="#f97316", label="Final traced peel-chain output (20 BTC)"),
        mpatches.Patch(color="#93c5fd", label="Other consolidation inputs"),
        mpatches.Patch(color="#9ca3af", label="Consolidation transaction"),
        mpatches.Patch(color="#22c55e", label="Consolidated output"),
    ]

    ax.legend(handles=legend_handles, loc="upper right")

    ax.set_title(
        "Consolidation phase: final peel-chain output merges into a larger transaction",
        pad=18,
        fontsize=13,
    )

    ax.set_xlim(-3.6, 3.6)
    ax.set_ylim(-3, 3)

    ax.axis("off")
    fig.tight_layout()

    return fig


# -----------------------------
# App UI
# -----------------------------
st.markdown('<div class="btc-coin">₿</div>', unsafe_allow_html=True)
st.title(CASE_NAME)
st.caption("A Bitcoin tracing case study showing a peel-chain phase followed by consolidation.")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
           Peel-chain laundering is a way criminals try to hide ownership of cryptocurrency funds. 
           Rather than moving one large balance directly, smaller amounts are split off over multiple transactions to make the linked addresses look unrelated.      
        </p>        
        <p>  
            This case study starts from the seed address <code>{SEED_ADDRESS}</code> and follows a high-value
            transaction output forward through the blockchain. The trace follows the continuing balance from one
            spent output to the next, then calculates the value separated from that continuing flow at each hop.
        </p>
        <p>
            This case shows a clear peel-chain pattern, where most of the value continues forward while smaller amounts are peeled away across successive transactions. 
            The traced path later ends when the remaining 20 BTC is merged into a much larger consolidation transaction, showing how laundering behaviour can shift from fragmentation to aggregation.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
st.header("How the trace works")

st.markdown(
    """
    <div class="case-card">
        <h3>Transaction-by-transaction tracing</h3>
        <p>
            The app does not group all outputs by address. It follows a specific transaction output, checks whether
            that output was spent and then moves into the transaction that spent it. The largest continuing output
            in that transaction becomes the next step in the chain.
        </p>
        <p>
            The peeled-off value is calculated as the difference between the balance entering the hop and the
            continuing balance leaving the hop.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Fixed display settings. This case study is intentionally hardcoded so it
# behaves like the Locky case study and opens directly into the analysis.
max_hops = DEFAULT_MAX_HOPS
graph_steps = DEFAULT_GRAPH_STEPS

try:
    with st.spinner("Fetching blockchain data and following the peel-chain path..."):
        peel_df, separated_df, trace_logs = trace_peel_chain_utxos(
            seed_address=SEED_ADDRESS,
            max_hops=max_hops,
        )
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()
except Exception as exc:
    st.error(f"Trace failed: {exc}")
    st.stop()

valid_steps = peel_df.dropna(subset=["Value Peeled Off"])
start_btc = float(peel_df.iloc[0]["Continuing BTC"]) if not peel_df.empty else 0.0
total_peeled = float(valid_steps["Value Peeled Off"].sum()) if not valid_steps.empty else 0.0
largest_peel = float(valid_steps["Value Peeled Off"].max()) if not valid_steps.empty else 0.0
final_btc = 0.0
if not valid_steps.empty:
    final_btc = float(valid_steps.iloc[-1]["Next Continuing BTC"])
elif not peel_df.empty:
    final_btc = float(peel_df.iloc[-1]["Continuing BTC"])

consolidation = get_consolidation_details(peel_df)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Starting flow", f"{start_btc:.4f} BTC")
col2.metric("Displayed hops", len(valid_steps))
col3.metric("Total peeled off", f"{total_peeled:.4f} BTC")
col4.metric("Largest peel", f"{largest_peel:.4f} BTC")
col5.metric("Final displayed flow", f"{final_btc:.4f} BTC")

if consolidation is not None:
    col6, col7, col8 = st.columns(3)
    col6.metric("Consolidation inputs", consolidation["input_count"])
    col7.metric("Consolidated output", f"{consolidation['total_output_btc']:.4f} BTC")
    col8.metric("Consolidation fee", f"{consolidation['fee_btc']:.6f} BTC")

st.markdown(
    f"""
    <div class="case-card">
        <h3>What the trace shows</h3>
        <p>
            The main flow begins at approximately <strong>{start_btc:.4f} BTC</strong> and is followed through
            successive spent outputs. Across the displayed path, <strong>{total_peeled:.4f} BTC</strong> is separated
            from the continuing flow.
        </p>
        <p>
            The important feature is the repeated forward movement: each hop spends the current output, creates a
            new continuing output and separates value away from the main path. The traced path then ends when the
            remaining 20 BTC output is swept into a larger consolidation transaction.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Peel-chain phase")
st.write(
    "The graph follows the continuing balance across successive spent outputs. "
    "The pink nodes show value separated from the main flow at each hop."
)
st.pyplot(draw_peel_graph(peel_df, graph_steps=graph_steps), use_container_width=True)

st.subheader("2. Peel-chain evidence table")
display_cols = [
    "Step",
    "Date Created",
    "Continuing Address",
    "Continuing BTC",
    "Spending Transaction",
    "Next Continuing BTC",
    "Value Peeled Off",
    "Transaction Fee BTC",
]
st.dataframe(peel_df[display_cols], use_container_width=True, hide_index=True)

with st.expander("Show peeled-off output details"):
    if separated_df.empty:
        st.write("No separated output details available for the displayed path.")
    else:
        st.dataframe(separated_df, use_container_width=True, hide_index=True)



st.subheader("3. Consolidation phase")

if consolidation is None:
    st.write("No consolidation transaction was identified at the end of the displayed path.")
else:
    st.write(
        f"After the peel-chain sequence, the final traced output of {consolidation['traced_btc']:.4f} BTC "
        f"is spent with other inputs in a consolidation transaction. The transaction combines "
        f"{consolidation['input_count']} inputs into {consolidation['output_count']} output, "
        f"with approximately {consolidation['total_output_btc']:.4f} BTC leaving as the consolidated output."
    )

    final_spending_txid = peel_df.iloc[-1]["Spending Transaction"]
    traced_input_value = float(peel_df.iloc[-1]["Continuing BTC"])

    st.pyplot(
        draw_consolidation_graph(
            final_spending_txid=final_spending_txid,
            traced_input_value=traced_input_value,
        ),
        use_container_width=True,
    )

    with st.expander("Show consolidation input and output tables"):
        st.markdown("**Consolidation inputs**")
        st.dataframe(consolidation["inputs"], use_container_width=True, hide_index=True)

        st.markdown("**Consolidation outputs**")
        st.dataframe(consolidation["outputs"], use_container_width=True, hide_index=True)




st.subheader("4. Transaction summary")
st.dataframe(build_summary_rows(peel_df), use_container_width=True, hide_index=True)


st.subheader("Interpretation note")
st.markdown(
    """
    <div class="case-card">
        <p>
            Blockchain tracing shows transaction movement. The labels in this case describe transaction structure:
            starting flow, continuing flow and value peeled off. They do not identify a real-world person.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)






st.subheader("References")
with st.expander("Show references and data sources"):
    st.markdown(
        """
        Blockstream (n.d.) *Blockstream API documentation*. Available at: https://blockstream.info/explorer-api.

        Cable, J. (2023) *conti-payments* [GitHub repository]. Available at: https://github.com/cablej/conti-payments.

        Gray, I.W., Cable, J., Brown, B., Cuiujuclu, V. and McCoy, D. (2023) *Money Over Morals: A Business Analysis of Conti Ransomware*. Available at: https://arxiv.org/abs/2304.11681.

        Kappos, G., Yousaf, H., Stütz, R., Rollet, S., Haslhofer, B. and Meiklejohn, S. (2022) 'How to Peel a Million: Validating and Expanding Bitcoin Clusters', *31st USENIX Security Symposium*.
        """
    )
