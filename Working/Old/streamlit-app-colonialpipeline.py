import requests
import pandas as pd
import time
import networkx as nx
import matplotlib.pyplot as plt


# -----------------------------
# CONFIG
# -----------------------------
case_name = "Colonial Pipeline"

# Starting Bitcoin address for the case
seed_address = "bc1qq2euq8pw950klpjcawuy4uj39ym43hs6cfsegq"

# Follow only a small number of hops to avoid graph explosion
MAX_HOPS = 2

# Main 63.7 BTC output address
main_flow_address = "bc1qpx7vyv5tp7dm0g475ev527krg764t73dh77gls"


# -----------------------------
# 1. Get all confirmed transactions for an address
# -----------------------------
def get_all_transactions(address):
    """
    Fetch all confirmed transactions for a Bitcoin address.
    Blockstream returns results in pages, so this loops until done.
    """
    all_txs = []
    last_seen = None

    while True:
        if last_seen:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain"

        res = requests.get(url)
        res.raise_for_status()
        data = res.json()

        print(f"Fetched {len(data)} transactions for {address}...")

        all_txs.extend(data)

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.2)

    return all_txs


# -----------------------------
# 2. Build transaction_inputs table
# -----------------------------
def build_transaction_inputs(all_txs):
    """
    Create a table where each row is one input to one transaction.
    Inputs show which addresses provided funds.
    """
    input_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vin in enumerate(tx["vin"]):
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

    return df_inputs


# -----------------------------
# 3. Build transaction_outputs table
# -----------------------------
def build_transaction_outputs(all_txs):
    """
    Create a table where each row is one output from one transaction.
    Outputs show where funds were sent.
    """
    output_rows = []

    for tx in all_txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for i, vout in enumerate(tx["vout"]):
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

    return df_outputs


# -----------------------------
# 4. Summarise outputs by address
# -----------------------------
def summarise_outputs(df_outputs):
    """
    Group outputs by receiving address.
    This shows which addresses received the most BTC overall.
    """
    summary = (
        df_outputs
        .groupby("Output Address")["Output Value"]
        .sum()
        .reset_index()
        .sort_values("Output Value", ascending=False)
        .reset_index(drop=True)
    )

    summary["BTC"] = (summary["Output Value"] / 100_000_000).round(4)

    return summary


# -----------------------------
# 5. Find large outputs
# -----------------------------
def find_large_outputs(df_outputs, min_btc=1):
    """
    Return only outputs above a BTC threshold.
    Useful for ignoring tiny outputs.
    """
    df_outputs = df_outputs.copy()
    df_outputs["BTC"] = df_outputs["Output Value"] / 100_000_000

    large_outputs = df_outputs[df_outputs["BTC"] > min_btc].sort_values(
        by="BTC",
        ascending=False
    )

    return large_outputs


# -----------------------------
# 6. Follow largest output path
# -----------------------------
def follow_largest_outputs(start_address, max_hops=2):
    """
    Follow the main money path by repeatedly selecting the largest output.

    This is a simple tracing rule:
    - look at the address
    - find where its transactions send value
    - follow the largest output forward
    """
    current_address = start_address
    hop_results = []

    for hop in range(1, max_hops + 1):
        print(f"\n--- HOP {hop}: analysing {current_address} ---")

        txs = get_all_transactions(current_address)

        df_inputs_hop = build_transaction_inputs(txs)
        df_outputs_hop = build_transaction_outputs(txs)

        summary = summarise_outputs(df_outputs_hop)

        print(f"\n--- Top outputs for hop {hop} ---")
        print(summary[["Output Address", "BTC"]].head(5))

        if summary.empty:
            print("No outputs found. Stopping trace.")
            break

        top_output = summary.iloc[0]

        hop_results.append({
            "hop": hop,
            "address": current_address,
            "next_address": top_output["Output Address"],
            "btc": top_output["BTC"],
            "summary": summary,
            "inputs": df_inputs_hop,
            "outputs": df_outputs_hop
        })

        next_address = top_output["Output Address"]

        if next_address == current_address:
            print("Largest output loops back to same address. Stopping trace.")
            break

        current_address = next_address

    return hop_results


# -----------------------------
# 7. Build peel-chain steps
# -----------------------------
def build_peel_steps(seed_address, seed_btc, main_flow_address, main_flow_btc, hop_results):
    """
    Build a clean table showing the dominant path of funds.

    This is easier to interpret than a full transaction graph.
    """
    steps = []

    steps.append({
        "Step": 0,
        "Address": seed_address,
        "Role": "Seed / ransom recipient",
        "BTC": seed_btc
    })

    steps.append({
        "Step": 1,
        "Address": main_flow_address,
        "Role": "Main forward flow",
        "BTC": main_flow_btc
    })

    for result in hop_results:
        steps.append({
            "Step": result["hop"] + 1,
            "Address": result["next_address"],
            "Role": "Next largest output",
            "BTC": result["btc"]
        })

    return pd.DataFrame(steps)


# -----------------------------
# 8. Draw simplified peel-chain graph
# -----------------------------
def draw_peel_chain_graph(peel_df):
    """
    Draw a simple path graph:
    seed → main flow → next largest output → next largest output
    """
    G = nx.DiGraph()
    labels = {}

    for _, row in peel_df.iterrows():
        node_id = f"Step {row['Step']}"

        labels[node_id] = (
            f"Step {row['Step']}\n"
            f"{row['Role']}\n"
            f"{row['BTC']} BTC"
        )

        G.add_node(node_id)

    for i in range(len(peel_df) - 1):
        G.add_edge(f"Step {i}", f"Step {i + 1}")

    plt.figure(figsize=(14, 5))

    pos = nx.shell_layout(G)

    nx.draw(
        G,
        pos,
        with_labels=False,
        node_size=3500,
        node_color="lightblue",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=20
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8
    )

    plt.title("Colonial Pipeline: Simplified Peel-Chain / Main Flow", pad=20)
    plt.show()


# -----------------------------
# RUN ANALYSIS
# -----------------------------

all_txs = get_all_transactions(seed_address)

df_inputs = build_transaction_inputs(all_txs)
df_outputs = build_transaction_outputs(all_txs)

outputs_summary = summarise_outputs(df_outputs)

print("\n--- Output Summary ---")
print(outputs_summary[["Output Address", "BTC"]].head(10))

large_outputs = find_large_outputs(df_outputs)

print("\n--- Large Outputs Over 1 BTC ---")
print(large_outputs[["Transaction ID", "Timestamp", "Output Address", "BTC"]])

# Get BTC amount received by the seed address
seed_btc = outputs_summary.loc[
    outputs_summary["Output Address"] == seed_address,
    "BTC"
].iloc[0]

# Get BTC amount for the main 63.7 BTC forward flow
main_flow_btc = outputs_summary.loc[
    outputs_summary["Output Address"] == main_flow_address,
    "BTC"
].iloc[0]

# Follow the main value path
hop_results = follow_largest_outputs(main_flow_address, MAX_HOPS)

# Build simple peel-chain summary table
peel_df = build_peel_steps(
    seed_address=seed_address,
    seed_btc=seed_btc,
    main_flow_address=main_flow_address,
    main_flow_btc=main_flow_btc,
    hop_results=hop_results
)

print("\n--- Peel Chain / Main Flow Summary ---")
print(peel_df)

# Draw simplified peel-chain graph
draw_peel_chain_graph(peel_df)