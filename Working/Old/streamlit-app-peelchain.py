import requests
import pandas as pd
import time
import networkx as nx
import matplotlib.pyplot as plt


# -----------------------------
# CONFIG
# -----------------------------

case_name = "Dharma / Xorist"

seed_address = "1NJNG57hFPPcmSmFYbxKmL33uc5nLwYLCK"

BRANCH_TOP_N = 3
BRANCH_MAX_HOPS = 3
BRANCH_MAX_PAGES_PER_ADDRESS = 2

MAX_HOPS = 15
GRAPH_STEPS = 6
MIN_BTC = 0.001


# -----------------------------
# 1. Get all confirmed transactions for an address
# -----------------------------
def get_all_transactions(address, max_pages=None):
    all_txs = []
    last_seen = None
    page_count = 0

    while True:
        if last_seen:
            url = f"https://blockstream.info/api/address/{address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{address}/txs/chain"

        for attempt in range(3):
            try:
                res = requests.get(url, timeout=20)
                res.raise_for_status()
                data = res.json()
                break
            except requests.exceptions.RequestException:
                print(f"Request failed, retrying... attempt {attempt + 1}/3")
                time.sleep(2)
        else:
            print("Could not fetch more transactions. Stopping here.")
            break

        print(f"Fetched {len(data)} transactions for {address}...")
        all_txs.extend(data)

        page_count += 1

        if max_pages is not None and page_count >= max_pages:
            print(f"Reached max_pages={max_pages}. Stopping fetch for this address.")
            break

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.5)

    return all_txs


# -----------------------------
# 2. Build transaction_inputs table
# -----------------------------
def build_transaction_inputs(all_txs):
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
    summary = (
        df_outputs
        .groupby("Output Address")["Output Value"]
        .sum()
        .reset_index()
        .sort_values("Output Value", ascending=False)
        .reset_index(drop=True)
    )

    summary["BTC"] = (summary["Output Value"] / 100_000_000).round(8)

    return summary


# -----------------------------
# 5. Find outputs above threshold
# -----------------------------
def find_large_outputs(df_outputs, min_btc=0.001):
    df_outputs = df_outputs.copy()
    df_outputs["BTC"] = df_outputs["Output Value"] / 100_000_000

    return df_outputs[df_outputs["BTC"] >= min_btc].sort_values(
        by="BTC",
        ascending=False
    )


# -----------------------------
# 6. Follow peel-chain path
# -----------------------------
def follow_largest_outputs(start_address, max_hops=15, min_btc=0.001):
    current_address = start_address
    hop_results = []
    seen_addresses = set()

    print("\n--- Following money (this may take a few seconds) ---")

    for hop in range(1, max_hops + 1):
        print(f"\n--- HOP {hop}/{max_hops}: analysing {current_address} ---")
        print("Calculating next step...")

        if current_address in seen_addresses:
            print("Address already seen. Peel chain likely looped. Stopping trace.")
            break

        seen_addresses.add(current_address)

        txs = get_all_transactions(current_address)

        df_inputs_hop = build_transaction_inputs(txs)
        df_outputs_hop = build_transaction_outputs(txs)

        summary = summarise_outputs(df_outputs_hop)
        filtered = summary[summary["BTC"] >= min_btc].reset_index(drop=True)

        print(f"\n--- Top outputs for hop {hop} ---")
        print(filtered[["Output Address", "BTC"]].head(10))

        if filtered.empty:
            print("No outputs above threshold. Stopping trace.")
            break

        candidates = filtered[
            filtered["Output Address"] != current_address
        ].reset_index(drop=True)

        if candidates.empty:
            print("No forward address found. Stopping trace.")
            break

        top_output = candidates.iloc[0]
        next_address = top_output["Output Address"]
        current_btc = top_output["BTC"]

        if hop_results:
            previous_btc = hop_results[-1]["btc"]

            if current_btc > previous_btc:
                print("Flow increased. Likely no longer a clean peel chain. Stopping trace.")
                break

            if (previous_btc - current_btc) > previous_btc * 0.2:
                print("Large drop detected — likely exit to service. Stopping trace.")
                break

            if current_btc < 0.01:
                print("Value too small — likely dust/noise. Stopping trace.")
                break

        hop_results.append({
            "hop": hop,
            "address": current_address,
            "next_address": next_address,
            "btc": current_btc,
            "summary": filtered,
            "inputs": df_inputs_hop,
            "outputs": df_outputs_hop
        })

        current_address = next_address

    print("\n--- Trace complete ---")
    print(f"Total hops analysed: {len(hop_results)}")

    return hop_results


# -----------------------------
# 7. Follow limited branches
# -----------------------------
def trace_top_branches(start_address, max_hops=3, top_n=3, min_btc=0.001):
    results = []
    queue = [(start_address, 0)]
    seen = set()

    while queue:
        current_address, depth = queue.pop(0)

        if depth >= max_hops:
            continue

        if current_address in seen:
            continue

        seen.add(current_address)

        print(f"\nTracing branches from {current_address} at depth {depth + 1}")

        # Branch tracing is capped so high-activity addresses do not run forever
        txs = get_all_transactions(
            current_address,
            max_pages=BRANCH_MAX_PAGES_PER_ADDRESS
        )

        is_high_activity = len(txs) >= 50

        df_outputs_branch = build_transaction_outputs(txs)
        summary = summarise_outputs(df_outputs_branch)

        filtered = summary[
            (summary["BTC"] >= min_btc) &
            (summary["Output Address"] != current_address)
        ].reset_index(drop=True)

        top_outputs = filtered.head(top_n)

        for i, row in top_outputs.iterrows():
            btc_value = row["BTC"]

            if is_high_activity or btc_value > 1000:
                label = "Service / Exchange"
            elif i == 0:
                label = "Main flow"
            elif btc_value > 1:
                label = "Branch"
            else:
                label = "Peel"

            results.append({
                "Depth": depth + 1,
                "From Address": current_address,
                "To Address": row["Output Address"],
                "BTC": btc_value,
                "Type": label,
                "High Activity": is_high_activity
            })

            # Keep expanding, but only up to BRANCH_MAX_HOPS
            queue.append((row["Output Address"], depth + 1))

    return pd.DataFrame(results)


# -----------------------------
# 8. Build peel-chain steps
# -----------------------------
def build_peel_steps(seed_address, seed_btc, main_flow_address, main_flow_btc, hop_results):
    steps = [
        {
            "Step": 0,
            "Address": seed_address,
            "Role": "Seed / collection address",
            "BTC": seed_btc
        },
        {
            "Step": 1,
            "Address": main_flow_address,
            "Role": "Main forward flow",
            "BTC": main_flow_btc
        }
    ]

    for result in hop_results:
        steps.append({
            "Step": result["hop"] + 1,
            "Address": result["next_address"],
            "Role": "Next largest output",
            "BTC": result["btc"]
        })

    return pd.DataFrame(steps)


# -----------------------------
# 9. Detect peeled amounts
# -----------------------------
def add_peeled_amounts(peel_df):
    peel_df = peel_df.copy()

    peel_df["Next BTC"] = peel_df["BTC"].shift(-1)
    peel_df["Estimated Peeled BTC"] = peel_df["BTC"] - peel_df["Next BTC"]
    peel_df["Estimated Peeled BTC"] = peel_df["Estimated Peeled BTC"].round(6)

    peel_df.loc[peel_df["Next BTC"].isna(), "Estimated Peeled BTC"] = None
    peel_df.loc[peel_df["Step"] == 0, "Estimated Peeled BTC"] = None

    return peel_df


# -----------------------------
# 10. Draw simplified peel-chain graph
# -----------------------------
def draw_peel_chain_graph(peel_df):
    G = nx.DiGraph()
    labels = {}
    edge_labels = {}
    pos = {}

    for i, row in peel_df.iterrows():
        main_node = f"Step {row['Step']}"
        pos[main_node] = (i * 4, 1)

        if row["Step"] == 0:
            role_text = "Entry (collection)"
        elif row["Step"] == 1:
            role_text = "Peel chain starts"
        else:
            role_text = "Peel chain"

        labels[main_node] = (
            f"Step {row['Step']}\n"
            f"{role_text}\n"
            f"{round(row['BTC'], 4)} BTC"
        )

        G.add_node(main_node)

    for i in range(len(peel_df) - 1):
        G.add_edge(f"Step {i}", f"Step {i + 1}")

    for i, row in peel_df.iterrows():
        peeled_value = row.get("Estimated Peeled BTC")

        if pd.notna(peeled_value) and peeled_value > 0:
            peel_node = f"Peel {row['Step']}"
            source = f"Step {row['Step']}"

            pos[peel_node] = (i * 4, 0)
            labels[peel_node] = f"Peeled\n{round(peeled_value, 4)} BTC"

            G.add_node(peel_node)
            G.add_edge(source, peel_node)

            edge_labels[(source, peel_node)] = f"{round(peeled_value, 4)} BTC"

    plt.figure(figsize=(22, 6))

    nx.draw(
        G,
        pos,
        with_labels=False,
        node_size=3000,
        node_color="lightblue",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=18
    )

    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7)

    plt.title("Dharma / Xorist Peel Chain", pad=20)
    plt.axis("off")
    plt.show()


# -----------------------------
# 11. Print peel interpretation
# -----------------------------
def print_peel_interpretation(peel_df):
    print("\n--- Peel Interpretation ---")

    for i in range(len(peel_df) - 1):
        current = peel_df.iloc[i]
        next_row = peel_df.iloc[i + 1]

        if pd.notna(current["Estimated Peeled BTC"]):
            print(
                f"Step {current['Step']} → {next_row['Step']}: "
                f"{round(current['BTC'], 4)} → {round(next_row['BTC'], 4)} BTC "
                f"(peeled ~{round(current['Estimated Peeled BTC'], 4)} BTC)"
            )


# -----------------------------
# 12. Print peel statistics
# -----------------------------
def print_peel_statistics(peel_df):
    print("\n--- Peel Statistics Summary (Full Trace) ---")

    valid_peels = peel_df["Estimated Peeled BTC"].dropna()
    valid_peels = valid_peels[valid_peels > 0]

    if valid_peels.empty:
        print("No peel events detected.")
        return

    print(f"Number of peel events: {len(valid_peels)}")
    print(f"Total BTC peeled: {round(valid_peels.sum(), 4)} BTC")
    print(f"Average peel size: {round(valid_peels.mean(), 4)} BTC")
    print(f"Largest peel: {round(valid_peels.max(), 4)} BTC")
    print(f"Smallest peel: {round(valid_peels.min(), 4)} BTC")
    print(f"Maximum depth analysed: {MAX_HOPS} hops")

    if len(peel_df) > 1:
        percentage = (valid_peels.sum() / peel_df.iloc[1]["BTC"]) * 100
        print(f"Percentage of total flow peeled: {round(percentage, 2)}%")


# -----------------------------
# 13. Select one peel event for deeper analysis
# -----------------------------

def select_largest_peel_event(peel_df):
    """
    Select the peel-chain step with the largest estimated peeled amount.

    This gives us one meaningful case example to inspect more deeply,
    instead of trying to follow every branch.
    """

    valid_peels = peel_df.dropna(subset=["Estimated Peeled BTC"])
    valid_peels = valid_peels[valid_peels["Estimated Peeled BTC"] > 0]

    if valid_peels.empty:
        print("No valid peel event found for deeper analysis.")
        return None

    largest_peel = valid_peels.loc[
        valid_peels["Estimated Peeled BTC"].idxmax()
    ]

    print("\n--- Selected Peel Event for Deeper Analysis ---")
    print(f"Step: {largest_peel['Step']}")
    print(f"Address: {largest_peel['Address']}")
    print(f"BTC before peel: {round(largest_peel['BTC'], 6)}")
    print(f"Estimated peeled amount: {round(largest_peel['Estimated Peeled BTC'], 6)} BTC")

    return largest_peel


def inspect_selected_peel_address(address, min_btc=0.001):
    """
    Inspect the selected address in more detail.

    This shows where value went from that address and whether it:
    - continued as a main flow
    - split into branches
    - moved to a high-activity/service-like address
    """

    print("\n--- Inspecting Selected Peel Address ---")
    print(f"Address: {address}")

    txs = get_all_transactions(address, max_pages=3)

    df_outputs = build_transaction_outputs(txs)
    summary = summarise_outputs(df_outputs)

    filtered = summary[
        (summary["BTC"] >= min_btc) &
        (summary["Output Address"] != address)
    ].reset_index(drop=True)

    print("\n--- Top Outputs from Selected Peel Address ---")
    print(filtered[["Output Address", "BTC"]].head(10))

    print("\n--- Interpretation of Selected Peel Event ---")

    if filtered.empty:
        print("No meaningful onward outputs found.")
        return filtered

    top_output = filtered.iloc[0]
    total_forwarded = filtered["BTC"].sum()

    print(f"Largest onward output: {round(top_output['BTC'], 6)} BTC")
    print(f"Total meaningful onward outputs: {round(total_forwarded, 6)} BTC")
    print(f"Number of onward outputs above threshold: {len(filtered)}")

    if len(filtered) == 1:
        print("This looks like the peel chain continues in a mostly linear path.")
    elif len(filtered) <= 3:
        print("This shows limited branching from the selected peel event.")
    else:
        print("This shows broader distribution, suggesting the flow becomes less linear here.")

    return filtered


# -----------------------------
# RUN ANALYSIS
# -----------------------------

all_txs = get_all_transactions(seed_address)

df_inputs = build_transaction_inputs(all_txs)
df_outputs = build_transaction_outputs(all_txs)

outputs_summary = summarise_outputs(df_outputs)

print("\n--- Output Summary ---")
print(outputs_summary[["Output Address", "BTC"]].head(10))

large_outputs = find_large_outputs(df_outputs, min_btc=MIN_BTC)

print(f"\n--- Outputs Over {MIN_BTC} BTC ---")
print(large_outputs[["Transaction ID", "Timestamp", "Output Address", "BTC"]].head(20))

seed_btc = outputs_summary.loc[
    outputs_summary["Output Address"] == seed_address,
    "BTC"
].iloc[0]

main_flow_row = outputs_summary[
    outputs_summary["Output Address"] != seed_address
].iloc[0]

main_flow_address = main_flow_row["Output Address"]
main_flow_btc = main_flow_row["BTC"]

print("\n--- Entry / Collection Summary ---")
print(f"Seed address: {seed_address}")
print(f"Total received: {round(seed_btc, 4)} BTC")
print(f"Main forward address: {main_flow_address}")
print(f"Main forward amount: {round(main_flow_btc, 4)} BTC")

print("\nInterpretation:")
print("Funds are first collected at the seed address (entry point),")
print("then consolidated and moved into a peel chain starting at Step 1.")

hop_results = follow_largest_outputs(
    start_address=main_flow_address,
    max_hops=MAX_HOPS,
    min_btc=MIN_BTC
)

peel_df = build_peel_steps(
    seed_address=seed_address,
    seed_btc=seed_btc,
    main_flow_address=main_flow_address,
    main_flow_btc=main_flow_btc,
    hop_results=hop_results
)

peel_df = add_peeled_amounts(peel_df)

print("\n--- Peel Chain / Main Flow Summary ---")
print(peel_df[["Step", "Address", "Role", "BTC", "Estimated Peeled BTC"]])

print_peel_interpretation(peel_df)
print_peel_statistics(peel_df)


selected_peel = select_largest_peel_event(peel_df)

if selected_peel is not None:
    selected_outputs = inspect_selected_peel_address(
        address=selected_peel["Address"],
        min_btc=MIN_BTC
    )

print("\nOpening graph window. Close the graph to continue.")
draw_peel_chain_graph(peel_df.head(GRAPH_STEPS))

print("\n--- Limited Branch Trace ---")

branch_df = trace_top_branches(
    start_address=main_flow_address,
    max_hops=BRANCH_MAX_HOPS,
    top_n=BRANCH_TOP_N,
    min_btc=MIN_BTC
)

print(branch_df)

if not branch_df.empty:
    print("\n--- Branch Type Counts ---")
    print(branch_df["Type"].value_counts())