import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


API_BASE = "https://blockstream.info/api"
SATOSHIS_PER_BTC = 100_000_000


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


def sats_to_btc(value):
    if value is None:
        return 0.0
    return value / SATOSHIS_PER_BTC


def get_json(url, timeout=20):
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def fetch_address_txs(address, max_pages=2, delay=0.25):
    all_txs = []
    last_seen_txid = None

    for _ in range(max_pages):
        if last_seen_txid:
            url = f"{API_BASE}/address/{address}/txs/chain/{last_seen_txid}"
        else:
            url = f"{API_BASE}/address/{address}/txs/chain"

        txs = get_json(url)

        if not txs:
            break

        all_txs.extend(txs)

        if len(txs) < 25:
            break

        last_seen_txid = txs[-1].get("txid")
        time.sleep(delay)

    return all_txs


def input_addresses(tx):
    addresses = []

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout") or {}
        address = prevout.get("scriptpubkey_address")
        if address:
            addresses.append(address)

    return addresses


def output_addresses_and_values(tx):
    outputs = []

    for vout in tx.get("vout", []):
        address = vout.get("scriptpubkey_address")
        value_btc = sats_to_btc(vout.get("value"))
        if address:
            outputs.append((address, value_btc))

    return outputs


def address_input_value(tx, address):
    total = 0.0

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout") or {}
        if prevout.get("scriptpubkey_address") == address:
            total += sats_to_btc(prevout.get("value"))

    return total


def address_output_value(tx, address):
    total = 0.0

    for vout in tx.get("vout", []):
        if vout.get("scriptpubkey_address") == address:
            total += sats_to_btc(vout.get("value"))

    return total


def classify_level(score):
    if score >= 4:
        return "High"
    if score >= 2:
        return "Medium"
    return "Low"


def repeated_equal_outputs(outputs, min_repeats=3):
    rounded_values = [round(value, 8) for _, value in outputs if value > 0]

    if not rounded_values:
        return False

    counts = Counter(rounded_values)
    _, count = counts.most_common(1)[0]

    return count >= min_repeats


def is_peel_like(outputs):
    values = sorted([value for _, value in outputs if value > 0], reverse=True)

    if len(values) != 2:
        return False

    large, small = values

    if small == 0:
        return False

    return large >= small * 5


def analyse_clustering(txs, address):
    score = 0
    reasons = []

    multi_input_txs = 0
    large_input_group_txs = 0
    co_spent_addresses = Counter()

    for tx in txs:
        inputs = input_addresses(tx)

        if address in inputs:
            unique_inputs = sorted(set(inputs))

            if len(unique_inputs) >= 2:
                multi_input_txs += 1
                score += 1

                for other in unique_inputs:
                    if other != address:
                        co_spent_addresses[other] += 1

            if len(unique_inputs) >= 5:
                large_input_group_txs += 1
                score += 1

    repeated_cospend = [addr for addr, count in co_spent_addresses.items() if count >= 2]

    if repeated_cospend:
        score += 1

    if multi_input_txs:
        reasons.append(f"This address was spent together with other input addresses in {multi_input_txs} transaction(s).")

    if large_input_group_txs:
        reasons.append(f"{large_input_group_txs} transaction(s) involved a larger group of input addresses, which may be worth a closer look.")

    if repeated_cospend:
        reasons.append("Some addresses were co-spent with this address more than once, which strengthens the clustering clue.")

    if not reasons:
        reasons.append("Nothing in the loaded transactions strongly suggests clustering behaviour.")

    return score, reasons


def analyse_peel_chain(txs, address):
    score = 0
    reasons = []

    outgoing_count = 0
    peel_like_count = 0

    for tx in txs:
        sent_by_address = address_input_value(tx, address)

        if sent_by_address > 0:
            outgoing_count += 1
            outputs = output_addresses_and_values(tx)

            if is_peel_like(outputs):
                peel_like_count += 1
                score += 2

    if outgoing_count >= 3:
        score += 1
        reasons.append(f"This address has {outgoing_count} outgoing transaction(s) in the loaded data.")

    if peel_like_count:
        reasons.append(
            f"{peel_like_count} outgoing transaction(s) had a peel-chain-like shape: most value continued forward while a smaller amount was separated."
        )

    if peel_like_count >= 2:
        score += 1
        reasons.append("More than one transaction shows a similar pattern, which makes the clue more interesting.")

    if not reasons:
        reasons.append("Nothing in the loaded transactions strongly suggests peel-chain behaviour.")

    return score, reasons


def analyse_mixer_like(txs):
    score = 0
    reasons = []

    high_input_output_txs = 0
    equal_output_txs = 0
    high_output_txs = 0

    for tx in txs:
        inputs = input_addresses(tx)
        outputs = output_addresses_and_values(tx)

        unique_input_count = len(set(inputs))
        output_count = len(outputs)

        if unique_input_count >= 5 and output_count >= 5:
            high_input_output_txs += 1
            score += 1

        if output_count >= 10:
            high_output_txs += 1
            score += 1

        if repeated_equal_outputs(outputs, min_repeats=3):
            equal_output_txs += 1
            score += 2

    if high_input_output_txs:
        reasons.append(f"{high_input_output_txs} transaction(s) had many inputs and many outputs, which can make tracing more difficult.")

    if high_output_txs:
        reasons.append(f"{high_output_txs} transaction(s) had a large number of outputs.")

    if equal_output_txs:
        reasons.append(f"{equal_output_txs} transaction(s) had repeated equal-value outputs, a pattern often worth clocking in mixer-style transactions.")

    if not reasons:
        reasons.append("Nothing in the loaded transactions strongly suggests mixer-like behaviour.")

    return score, reasons


def build_summary_table(txs, address):
    rows = []

    for tx in txs:
        txid = tx.get("txid", "")
        status = tx.get("status", {})
        block_time = status.get("block_time")

        if block_time:
            time_text = pd.to_datetime(block_time, unit="s", utc=True).strftime("%Y-%m-%d %H:%M UTC")
        else:
            time_text = "Unconfirmed / unknown"

        received = address_output_value(tx, address)
        spent = address_input_value(tx, address)

        if received > 0 and spent > 0:
            direction = "Both"
        elif received > 0:
            direction = "Incoming"
        elif spent > 0:
            direction = "Outgoing"
        else:
            direction = "Related"

        rows.append(
            {
                "Transaction ID": txid,
                "Time": time_text,
                "Direction": direction,
                "Inputs": len(set(input_addresses(tx))),
                "Outputs": len(output_addresses_and_values(tx)),
                "Received BTC": round(received, 8),
                "Spent BTC": round(spent, 8),
            }
        )

    return pd.DataFrame(rows)


st.title("₿ Suspicious activity checker")
st.caption('A quick "does this pass the vibe check?" screen for Bitcoin addresses.')

st.write(
    "Enter a Bitcoin address and this page will look for basic blockchain clues linked to the case studies: "
    "clustering, peel-chain-style movement and mixer-like activity."
)

st.warning(
    "Blockchain tracing is a powerful tool, but it is not a crystal ball. "
    "This checker can highlight patterns that deserve a closer look, but it cannot identify who controls an address or prove that a crime occurred."
)

with st.expander("What is this checker looking for?"):
    st.markdown(
        """
        **Clustering clues** look for addresses being spent together in the same transaction. This can suggest that the same person, wallet or group may control them.

        **Peel-chain clues** look for the classic pattern where most of the Bitcoin keeps moving forward while smaller amounts are repeatedly separated.

        **Mixer-like clues** look for transactions with lots of inputs, lots of outputs or repeated equal-value outputs. These patterns can make it harder to connect a sender to a receiver.

        These are simple screening rules. Think of them as a first-pass vibe check, not a final investigation finding.
        """
    )

sample_addresses = {
    "Choose a sample or enter your own": "",
    "Locky ransomware sample": "178HGmCfR26dSSiFxJQah1U588p2CjgX7f",
    "Custom": "",
}

sample_choice = st.selectbox("Pick a trail to follow", list(sample_addresses.keys()))
default_address = sample_addresses.get(sample_choice, "")

address = st.text_input(
    "Bitcoin address",
    value=default_address,
    placeholder="Paste a Bitcoin address here"
).strip()

max_pages = st.slider(
    "How much of the money trail should be loaded?",
    min_value=1,
    max_value=4,
    value=2,
    help="Each page loads up to 25 confirmed transactions. More pages gives the checker more to inspect, but may take longer."
)

if st.button("Run the vibe check"):
    if not address:
        st.error("Please enter a Bitcoin address first.")
        st.stop()

    with st.spinner("Loading recent confirmed transactions from Blockstream..."):
        txs = fetch_address_txs(address, max_pages=max_pages)

    if not txs:
        st.error(
            "No confirmed transactions were loaded for this address. "
            "Check the address or try again."
        )
        st.stop()

    st.success(f"Loaded {len(txs)} confirmed transaction(s).")

    clustering_score, clustering_reasons = analyse_clustering(txs, address)
    peel_score, peel_reasons = analyse_peel_chain(txs, address)
    mixer_score, mixer_reasons = analyse_mixer_like(txs)

    clustering_level = classify_level(clustering_score)
    peel_level = classify_level(peel_score)
    mixer_level = classify_level(mixer_score)

    st.header("What should you clock?")

    st.markdown(
        f"""
        <div class="case-card">
            <h3>Quick read</h3>
            <p><strong>Clustering clues:</strong> {clustering_level}</p>
            <p><strong>Peel-chain clues:</strong> {peel_level}</p>
            <p><strong>Mixer-like clues:</strong> {mixer_level}</p>
            <p class="small-note">
                Low, Medium and High are based on simple clue counts from the loaded transactions. They are useful for deciding where to look next, not for making final claims.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Clustering", clustering_level)

    with col2:
        st.metric("Peel chain", peel_level)

    with col3:
        st.metric("Mixer-like", mixer_level)

    st.header("Why did the checker flag these?")

    with st.expander("Clustering clues", expanded=True):
        for reason in clustering_reasons:
            st.write(f"- {reason}")

    with st.expander("Peel-chain clues", expanded=True):
        for reason in peel_reasons:
            st.write(f"- {reason}")

    with st.expander("Mixer-like clues", expanded=True):
        for reason in mixer_reasons:
            st.write(f"- {reason}")

    st.header("Loaded transaction summary")

    st.write(
        "These are the transactions the checker looked at. Copy a transaction ID into the Transaction Lookup page if you want to dig deeper."
    )

    summary_df = build_summary_table(txs, address)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.info(
        "Tip: A high score is not a verdict. It just means the address has patterns worth investigating further. Follow the money, then check the context."
    )
