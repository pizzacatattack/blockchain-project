"""
ChipMixer Mixer Case Study

This Streamlit app starts from a ChipMixer-linked coordinator-fee style address.

The goal is to find and display one transaction with strong mixer-like
structure:
- many inputs
- many outputs
- repeated or similar output amounts
- weak direct mapping between a specific input and a specific output

This is a fixed case-study app, not a general address explorer.
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
CASE_NAME = "ChipMixer Mixer Case Study"

# Address discussed earlier as appearing in thousands of mixer transactions.
SEED_ADDRESS = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"

BACKUP_ADDRESS = "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw"

REQUEST_TIMEOUT_SECONDS = 20
SATOSHIS_PER_BTC = 100_000_000
MAX_ADDRESS_PAGES = 6

MAX_GRAPH_INPUTS = 10
MAX_GRAPH_OUTPUTS = 12

BLOCKSTREAM_URL = "https://blockstream.info"


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


def get_input_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vin in enumerate(tx.get("vin", [])):
        prevout = vin.get("prevout") or {}
        address = prevout.get("scriptpubkey_address")
        value_btc = sats_to_btc(prevout.get("value", 0))

        rows.append({
            "Input Index": index,
            "Input Address": address,
            "Input BTC": value_btc,
            "Seed Address Input": address == SEED_ADDRESS,
        })
    return rows


def get_output_rows(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for index, vout in enumerate(tx.get("vout", [])):
        address = safe_address(vout)
        value_btc = sats_to_btc(vout.get("value", 0))

        rows.append({
            "Output Index": index,
            "Output Address": address,
            "Output BTC": value_btc,
            "Seed Address Output": address == SEED_ADDRESS,
        })
    return rows


def repeated_output_summary(outputs: List[Dict[str, Any]], decimals: int = 8) -> pd.DataFrame:
    """Group output values to detect repeated denominations."""
    if not outputs:
        return pd.DataFrame(columns=["Rounded Output BTC", "Count", "Total BTC"])

    df = pd.DataFrame(outputs)
    df["Rounded Output BTC"] = df["Output BTC"].round(decimals)

    grouped = (
        df.groupby("Rounded Output BTC", dropna=False)
        .agg(Count=("Output BTC", "count"), Total_BTC=("Output BTC", "sum"))
        .reset_index()
        .rename(columns={"Total_BTC": "Total BTC"})
        .sort_values(["Count", "Total BTC"], ascending=False)
        .reset_index(drop=True)
    )

    return grouped


def transaction_score(tx: Dict[str, Any]) -> float:
    """Score transactions for visually strong mixer/mixer-like structure."""
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    input_count = len(inputs)
    output_count = len(outputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)

    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_outputs = repeated_df[repeated_df["Count"] >= 2]
    max_repeat_count = int(repeated_df["Count"].max()) if not repeated_df.empty else 0

    seed_involved = any(row["Seed Address Input"] for row in inputs) or any(row["Seed Address Output"] for row in outputs)

    score = 0

    # Mixer-style transactions are visually stronger with many inputs and outputs.
    score += input_count * 6
    score += output_count * 8

    # Repeated output amounts are very important for a mixer-style explanation.
    score += max_repeat_count * 25
    score += len(repeated_outputs) * 30

    # Avoid tiny/noisy transactions being selected just because they have repeats.
    score += min(total_output_btc, 50) * 0.4

    if seed_involved:
        score += 60

    # Penalise boring simple transactions.
    if input_count <= 2 or output_count <= 2:
        score -= 100

    if output_count < 5:
        score -= 60

    return score


def choose_case_transaction(address: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch transactions and select the most compelling mixer-like transaction."""
    info = get_address_info(address)
    txs = get_address_transactions(address, max_pages=MAX_ADDRESS_PAGES)

    if not txs:
        raise ValueError("No transactions were found for the ChipMixer-linked address.")

    best_tx = max(txs, key=transaction_score)
    return info, best_tx, txs


def build_address_summary(address: str, info: Dict[str, Any], txs: List[Dict[str, Any]]) -> pd.DataFrame:
    chain_stats = info.get("chain_stats", {})
    funded_btc = sats_to_btc(chain_stats.get("funded_txo_sum", 0))
    spent_btc = sats_to_btc(chain_stats.get("spent_txo_sum", 0))

    rows = [
        {"Metric": "ChipMixer-linked seed address", "Value": address},
        {"Metric": "Fetched transactions analysed", "Value": len(txs)},
        {"Metric": "Confirmed transaction count", "Value": chain_stats.get("tx_count", 0)},
        {"Metric": "Confirmed BTC received", "Value": btc(funded_btc)},
        {"Metric": "Confirmed BTC spent", "Value": btc(spent_btc)},
    ]
    return pd.DataFrame(rows)


def build_transaction_summary(tx: Dict[str, Any]) -> pd.DataFrame:
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    total_input_btc = sum(row["Input BTC"] for row in inputs)
    total_output_btc = sum(row["Output BTC"] for row in outputs)
    fee_btc = sats_to_btc(tx.get("fee", 0))

    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_values = repeated_df[repeated_df["Count"] >= 2]
    max_repeat = int(repeated_df["Count"].max()) if not repeated_df.empty else 0

    rows = [
        {"Metric": "Selected transaction", "Value": tx.get("txid")},
        {"Metric": "Date", "Value": format_date(tx.get("status", {}).get("block_time"))},
        {"Metric": "Input count", "Value": len(inputs)},
        {"Metric": "Output count", "Value": len(outputs)},
        {"Metric": "Total input BTC", "Value": btc(total_input_btc)},
        {"Metric": "Total output BTC", "Value": btc(total_output_btc)},
        {"Metric": "Transaction fee", "Value": btc(fee_btc)},
        {"Metric": "Repeated output values detected", "Value": len(repeated_values)},
        {"Metric": "Largest repeated output group", "Value": max_repeat},
    ]
    return pd.DataFrame(rows)


def draw_mixer_structure_graph(tx: Dict[str, Any]) -> plt.Figure:
    """Draw a simplified mixer-style transaction diagram for the report.

    This version uses labelled boxes instead of many small circular nodes.
    It is designed to be readable when pasted into a Word/PDF report.
    """
    inputs = get_input_rows(tx)
    outputs = get_output_rows(tx)

    total_input_btc = sum(row["Input BTC"] for row in inputs)

    seed_inputs = [row for row in inputs if row.get("Seed Address Input")]
    seed_input_btc = sum(row["Input BTC"] for row in seed_inputs)

    # Group repeated output amounts. These are the key mixer-style signal.
    repeated_df = repeated_output_summary(outputs, decimals=8)
    repeated_groups = repeated_df[repeated_df["Count"] >= 2].copy()
    repeated_groups = repeated_groups.sort_values(["Count", "Total BTC"], ascending=False)

    repeated_value_set = set(repeated_groups["Rounded Output BTC"].tolist())
    other_outputs = [
        row for row in outputs
        if round(row["Output BTC"], 8) not in repeated_value_set
    ]
    other_output_btc = sum(row["Output BTC"] for row in other_outputs)

    # Keep the four strongest repeated groups visible and group the rest.
    visible_repeats = repeated_groups.head(4)
    remaining_repeated = repeated_groups.iloc[4:]
    remaining_repeated_count = int(remaining_repeated["Count"].sum()) if not remaining_repeated.empty else 0
    remaining_repeated_btc = float(remaining_repeated["Total BTC"].sum()) if not remaining_repeated.empty else 0.0

    grouped_other_count = len(other_outputs) + remaining_repeated_count
    grouped_other_btc = other_output_btc + remaining_repeated_btc

    # -----------------------------
    # Drawing helpers
    # -----------------------------
    def add_box(ax, x, y, text, facecolor, width=2.05, height=0.72, fontsize=10):
        box = mpatches.FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.4,
            edgecolor="#374151",
            facecolor=facecolor,
        )
        ax.add_patch(box)
        ax.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=fontsize,
            fontweight="bold",
            color="#111827",
            linespacing=1.15,
        )
        return box

    def add_arrow(ax, x1, y1, x2, y2):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="-|>",
                color="#6b7280",
                linewidth=1.8,
                shrinkA=12,
                shrinkB=12,
                mutation_scale=18,
            ),
        )

    fig, ax = plt.subplots(figsize=(13, 7.2))

    # Input side
    if seed_inputs:
        seed_text = f"Seed input\n{seed_input_btc:.1f} BTC"
    else:
        seed_text = "Seed address\nused to find TX"

    add_box(ax, -4.4, 1.0, seed_text, "#F4C76B", width=1.95, height=0.70, fontsize=9.5)

    other_input_count = len(inputs) - len(seed_inputs)
    if other_input_count > 0:
        input_text = f"{len(inputs)} inputs\n{total_input_btc:.1f} BTC pooled"
    else:
        input_text = f"{len(inputs)} input\n{total_input_btc:.1f} BTC"
    add_box(ax, -4.4, -0.35, input_text, "#BFDDF2", width=2.15, height=0.82, fontsize=10)

    # Main transaction
    add_box(ax, -0.5, 0.0, "Mixer-style\ntransaction", "#D8D2F0", width=2.05, height=0.85, fontsize=10)

    # Output side
    output_positions = []
    output_labels = []

    y_values = [1.85, 0.95, 0.05, -0.85]
    for y, (_, row) in zip(y_values, visible_repeats.iterrows()):
        value = float(row["Rounded Output BTC"])
        count = int(row["Count"])
        total = float(row["Total BTC"])
        output_positions.append((3.6, y, "#A9D8B1"))
        output_labels.append(f"{count} outputs\n{value:.1f} BTC each\n{total:.1f} BTC total")

    if grouped_other_count > 0:
        output_positions.append((3.6, -1.85, "#D9F0DD"))
        output_labels.append(f"Other outputs\n{grouped_other_count} outputs\n{grouped_other_btc:.1f} BTC")

    for (x, y, colour), label in zip(output_positions, output_labels):
        add_box(ax, x, y, label, colour, width=2.25, height=0.78, fontsize=9.5)

    # Arrows
    if seed_inputs:
        add_arrow(ax, -3.35, 1.0, -1.55, 0.12)
    # If the seed address only helped locate the transaction, do not draw an arrow from it.
    add_arrow(ax, -3.35, -0.35, -1.55, -0.05)
    for x, y, _ in output_positions:
        add_arrow(ax, 0.55, 0.0, x - 1.15, y)

    # Title and summary
    ax.set_title(
        "Mixer-style transaction: pooled inputs and repeated outputs",
        fontsize=15,
        pad=18,
    )

    ax.text(
        -0.5,
        -2.8,
        f"Summary: {len(inputs)} inputs → 1 mixer-style transaction → {len(outputs)} outputs.",
        ha="center",
        va="center",
        fontsize=11,
        color="#374151",
    )

    ax.text(
        -4.4,
        -1.35,
        "The seed address was used to locate this case-study transaction.",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#4b5563",
    )

    ax.set_xlim(-5.8, 5.3)
    ax.set_ylim(-3.2, 2.5)
    ax.axis("off")
    fig.tight_layout()
    return fig

# -----------------------------
# App UI
# -----------------------------
st.title("₿ ChipMixer: mixing behaviour")
st.caption("A Bitcoin tracing case study showing how mixers make it harder to follow the money.")

st.markdown(
    f"""
    <div class="case-card">
        <h3>Case focus</h3>
        <p>
        ChipMixer was a cryptocurrency mixer designed to make tracing more difficult.
        </p>
         <p>
        Instead of a simple payment from one address to another, funds from many users are combined into a large pool and then redistributed. 
        Participants receive their Bitcoin back to fresh addresses, while the transaction often creates many small outputs with similar values. 
        </p>
        <p>
        The goal is to make it harder for investigators to connect a sender's original address to their new receiving address.
        </p>
        <p class="small-note">
            Seed address: <code>{SEED_ADDRESS}</code>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.header("Why this matters for tracing")
st.markdown(
    """
    <div class="case-card">
        <p>
            In a simple Bitcoin transaction, an investigator can often ask: where did the money come from, and where did it go next? Mixers are designed to make that question much harder to answer.
        </p>
        <p>
            When many users are pooled into one transaction and sent back out through many similar outputs, the direct link between sender and receiver starts to break down. The blockchain still shows movement, but the story becomes harder to read.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Loading ChipMixer-linked transaction data from Blockstream..."):
        address_info, selected_tx, address_txs = choose_case_transaction(SEED_ADDRESS)
except requests.exceptions.RequestException as exc:
    st.error(f"Could not fetch data from Blockstream: {exc}")
    st.stop()
except Exception as exc:
    st.error(f"Case loading failed: {exc}")
    st.stop()

inputs = get_input_rows(selected_tx)
outputs = get_output_rows(selected_tx)
repeated_df = repeated_output_summary(outputs, decimals=8)
repeated_values = repeated_df[repeated_df["Count"] >= 2]
total_output_btc = sum(row["Output BTC"] for row in outputs)

st.info(
    f"""
**What should you clock?**

• The selected transaction pools **{len(inputs)} inputs** into one transaction

• It then redistributes value across **{len(outputs)} outputs**

• The app detected **{len(repeated_values)} repeated output value groups**

• This is not a simple payment. It is a mixer-style transaction pattern that deserves a closer look
"""
)

st.markdown(
    f"""
    <div class="case-card">
        <h3>What does not pass the vibe check?</h3>
        <p>
            The selected transaction does not behave like a normal one-to-one payment. It combines many inputs and creates many outputs, including repeated output values that look deliberately standardised.
        </p>
        <p>
            This matters because repeated output sizes make it harder to directly match one input participant to one output recipient. The funds are still visible on the blockchain, but the simple money trail becomes much harder to follow.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Mixer-style transaction graph")
st.write(
    "This graph simplifies the transaction so the pattern is easier to clock. "
    "Many inputs are pooled into one transaction, then redistributed into many outputs. "
    "The repeated output amounts are the key clue: they make it harder to link one sender to one receiver."
)
st.pyplot(draw_mixer_structure_graph(selected_tx), use_container_width=True)

st.subheader("2. Selected transaction summary")
st.dataframe(build_transaction_summary(selected_tx), use_container_width=True, hide_index=True)

st.subheader("3. Repeated output values")
st.write(
    "This table shows the repeated BTC amounts found across the outputs. "
    "Repeated values can make the outputs look more alike, which makes the transaction harder to untangle."
)
st.dataframe(repeated_df.head(20), use_container_width=True, hide_index=True)

st.subheader("4. Seed address summary")
st.dataframe(build_address_summary(SEED_ADDRESS, address_info, address_txs), use_container_width=True, hide_index=True)

with st.expander("Show selected transaction inputs and outputs"):
    st.markdown("**Inputs**")
    st.dataframe(pd.DataFrame(inputs), use_container_width=True, hide_index=True)

    st.markdown("**Outputs**")
    st.dataframe(pd.DataFrame(outputs), use_container_width=True, hide_index=True)

st.subheader("Interpretation note")
st.markdown(
    """
    <div class="case-card">
        <p>
            Blockchain tracing is a powerful tool, but it is not a crystal ball. This case study highlights transaction structure: many inputs, many outputs and repeated output values.
        </p>
        <p>
            These patterns can point investigators in the right direction, but they do not prove who controlled each address or whether every participant was acting unlawfully.
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

        U.S. Department of Justice (2023) *Justice Department Investigation Leads to Takedown of Darknet Cryptocurrency Mixer that Processed Over $3 Billion of Unlawful Transactions*. Available at: https://www.justice.gov/archives/opa/pr/justice-department-investigation-leads-takedown-darknet-cryptocurrency-mixer-processed-over-3.

        Europol (2023) *One of the darkweb’s largest cryptocurrency laundromats washed out*. Available at: https://www.europol.europa.eu/media-press/newsroom/news/one-of-darkwebs-largest-cryptocurrency-laundromats-washed-out.
        """
    )
