import requests
import pandas as pd
import time
import networkx as nx
import matplotlib.pyplot as plt


#Locky is a well-researched ransomware case from 2016, infected millions of users worldwide
#Seed address here was just used for two transactions
#However, one of those transactions involved 29 other unique input addresses
#When multiple addresses are used for one input, those addresses likely all have the same owner/controlled by the same person or entity
#Used ChatGPT for this, which I will attribute
#Main piece of work for my project will then be the research paper I write to go along with my tool


# -----------------------------
# CONFIG
# -----------------------------
case_name = "Locky"
seed_address = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"


# -----------------------------
# 1. Get all confirmed transactions for a seed address (e.g. Locky address noted above)
# -----------------------------
def get_all_transactions(seed_address):
    all_txs = []
    last_seen = None

    while True:
        if last_seen:
            url = f"https://blockstream.info/api/address/{seed_address}/txs/chain/{last_seen}"
        else:
            url = f"https://blockstream.info/api/address/{seed_address}/txs/chain"

        res = requests.get(url)
        res.raise_for_status()
        data = res.json()

        print(f"Fetched {len(data)} transactions...")

        all_txs.extend(data)

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.2)

    return all_txs


# -----------------------------
# 2. Build transaction_inputs table
# -----------------------------

#All addresses that provided funds for each transaction
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

#All addresses that received funds from each transaction
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
# 4. Build small multi-input clusters
#    One set per transaction with >1 unique input address
# -----------------------------

#For each transaction, if it has more than one unique input address, group those addresses together into a cluster
def build_input_clusters(df_inputs):
    small_clusters = []

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

#If two clusters share at least one address, combine them into a bigger cluster
#This is because the addresses in the two clusters are very likely to have the same owner (not always true, will note exceptions)
def merge_overlapping_sets(list_of_sets):
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

#My dataset is the two transactions of my seed address, plus the data in my transaction_inputs and transaction_outputs tables
#Want to look at addresses that apear at least twice because they are more likely to be part a network and not just one-offs
def get_repeat_addresses(df_inputs, df_outputs, min_appearances=2):
    input_counts = df_inputs["Input Address"].dropna().value_counts()
    output_counts = df_outputs["Output Address"].dropna().value_counts()

    repeated_inputs = set(input_counts[input_counts >= min_appearances].index)
    repeated_outputs = set(output_counts[output_counts >= min_appearances].index)

    return repeated_inputs.union(repeated_outputs)


# -----------------------------
# 7. Addresses that are in merged clusters
# -----------------------------
def get_cluster_addresses(merged_clusters, min_cluster_size=2):
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

#Continue tracing addresses that are in the consolidated cluster
def choose_addresses_to_expand(df_inputs, df_outputs, merged_clusters, seed_address, min_appearances=2):
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

#Build dataframe of final cluster
def build_clusters_dataframe(merged_clusters):
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


# -----------------------------
# 10. Run the pipeline
# -----------------------------

#Run all steps from start to finish automatically
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
    min_appearances=2
)

df_clusters = build_clusters_dataframe(merged_clusters)


# -----------------------------
# 11. Console summaries
# -----------------------------

#Prints a summary of results
largest_cluster_size = max((len(c) for c in merged_clusters), default=0)

print("\n--- CASE SUMMARY ---")
print("Case name:", case_name)
print("Seed address:", seed_address)
print("Total transactions fetched:", len(all_txs))
print("Total input rows:", len(df_inputs))
print("Total output rows:", len(df_outputs))
print("Small cluster count:", len(small_clusters))
print("Merged cluster count:", len(merged_clusters))
print("Largest cluster size:", largest_cluster_size)
print("Addresses selected for expansion:", len(addresses_to_expand))

print("\n--- transaction_inputs ---")
print(df_inputs.head())

print("\n--- transaction_outputs ---")
print(df_outputs.head())

print("\n--- merged clusters dataframe ---")
print(df_clusters.head(20))

#Addresses to investigate and trace next (addresses in the merged cluster)
print("\n--- addresses to expand ---")
for addr in addresses_to_expand[:20]:
    print(addr)


print("\n--- transaction_outputs ---")
print(df_outputs.head())

# -----------------------------
# ADDRESS REUSE SUMMARY
# -----------------------------
input_counts = df_inputs["Input Address"].value_counts()

print("\n--- Top Reused Input Addresses ---")
print(input_counts.head(5))

print("\n--- merged clusters dataframe ---")
print(df_clusters.head(20))


# -----------------------------
# 12. Save tables to CSV
# -----------------------------
df_inputs.to_csv(f"{case_name}_transaction_inputs.csv", index=False)
df_outputs.to_csv(f"{case_name}_transaction_outputs.csv", index=False)
df_clusters.to_csv(f"{case_name}_clusters.csv", index=False)

df_clustered_addresses = pd.DataFrame({
    "Address": addresses_to_expand
})
df_clustered_addresses.to_csv(f"{case_name}_addresses_to_expand.csv", index=False)


# -----------------------------
# 13. Print sum received
# -----------------------------

#Print total received by all addresses in the cluster
cluster_addresses = set(df_clusters["Address"])

cluster_received = df_outputs[
    df_outputs["Output Address"].isin(cluster_addresses)
]

total_received = cluster_received["Output Value"].sum()

#Convert from satoshi to btc
total_received_btc = total_received / 100000000

print("Total Received (BTC)", f"{total_received_btc:.4f}")


# -----------------------------
# 14. Print sum received by each address plus top 5 receivers
# -----------------------------

#One address in this cluster received funds
#More interesting analysis will be who all the addresses in the cluster sent funds to
#Cluster received 3 BTC, sent 8 BTC -> forwarding funds
received_by_address = (
    cluster_received.groupby("Output Address")["Output Value"]
    .sum()
    .reset_index()
    .sort_values(by="Output Value", ascending=False)
)

received_by_address["BTC"] = received_by_address["Output Value"] / 100000000

print(received_by_address)

#Not that useful here but will use it later
top_5 = received_by_address.head(5)
print(top_5)
print("\n--- Top 5 Receiving Addresses ---")
print(top_5[["Output Address", "BTC"]])



# -----------------------------
# 15. Transaction flow graph
# -----------------------------

#Flow graph - shows movement

#Each transaction is a bridge node
#Bitcoin flows: input address → transaction → output address
#This structure reflects how Bitcoin actually works:
    #Inputs fund a transaction
    #Outputs distribute that value

#Blue dots = addresses
#Grey dots = transactions
#Arrows = flow of Bitcoin
#Funds from many input addresses were combined into one transaction, then split into two output addresses

# Create a directed graph
# Directed = edges have direction (money flows from A → B)
G = nx.DiGraph()

# -----------------------------
# ADD INPUT EDGES
# -----------------------------
# These represent: address → transaction
# (i.e. address is PROVIDING funds to the transaction)

for _, row in df_inputs.iterrows():
    G.add_edge(
        row["Input Address"],        # source node (address sending BTC)
        row["Transaction ID"],       # target node (transaction)
        value=row["Input Value"],    # store how much BTC was sent
        edge_type="input"            # label edge type (useful later)
    )

# -----------------------------
# ADD OUTPUT EDGES
# -----------------------------
# These represent: transaction → address
# (i.e. transaction sends BTC to this address)

for _, row in df_outputs.iterrows():
    G.add_edge(
        row["Transaction ID"],       # source node (transaction)
        row["Output Address"],       # target node (address receiving BTC)
        value=row["Output Value"],   # amount received
        edge_type="output"           # label edge type
    )

# -----------------------------
# GRAPH LAYOUT
# -----------------------------
# spring_layout positions nodes using a physics simulation
# nodes repel each other, edges act like springs
# result = more readable layout

plt.figure(figsize=(14, 10))  # make the graph bigger

pos = nx.spring_layout(
    G,
    k=0.5,       # spacing between nodes (higher = more spread out)
    seed=42      # ensures same layout every run (important for reproducibility)
)

# -----------------------------
# NODE COLOURING
# -----------------------------
# We colour addresses differently from transactions
# (basic heuristic: BTC addresses start with 1, 3, or bc1)

# -----------------------------
# NODE COLOURING
# -----------------------------
# We colour addresses differently from transactions
# (basic heuristic: BTC addresses start with 1, 3, or bc1)

seed = "178HGmCfR26dSSiFxJQah1U588p2CjgX7f"

node_colours = []
node_sizes = []

for node in G.nodes():
    if node == seed:
        node_colours.append("red")         # seed address
        node_sizes.append(700)             # make seed address larger
    elif str(node).startswith(("1", "3", "bc1")):
        node_colours.append("lightblue")   # address nodes
        node_sizes.append(400)
    else:
        node_colours.append("lightgrey")   # transaction nodes
        node_sizes.append(250)             # make transactions slightly smaller

# -----------------------------
# DRAW GRAPH
# -----------------------------
nx.draw(
    G,
    pos,
    with_labels=False,    # labels get messy quickly
    node_size=node_sizes,
    node_color=node_colours,
    arrows=True,          # show direction of BTC flow
    alpha=0.8             # slight transparency
)

# -----------------------------
# ADD SELECTIVE LABELS
# -----------------------------
# Only label the seed address and the main high-degree transaction
# This keeps the graph readable

labels = {}

for node in G.nodes():
    if node == seed:
        labels[node] = "Seed Address"
    elif not str(node).startswith(("1", "3", "bc1")) and G.degree(node) > 10:
        labels[node] = "Main Tx"

# nx.draw_networkx_labels(
#     G,
#     pos,
#     labels=labels,
#     font_size=9
# )

# -----------------------------
# ADD LEGEND
# -----------------------------
# Legend explains what each colour represents

import matplotlib.patches as mpatches

legend_handles = [
    mpatches.Patch(color="lightblue", label="Address"),
    mpatches.Patch(color="lightgrey", label="Transaction"),
    mpatches.Patch(color="red", label="Seed Address")
]

plt.legend(handles=legend_handles)

plt.title("Bitcoin Transaction Flow Graph")
plt.show()


# -----------------------------
# 16. Cluster graph
# -----------------------------

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
    cluster = list(cluster)

    # connect every pair of addresses in the cluster
    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            cluster_graph.add_edge(
                cluster[i],   # address A
                cluster[j]    # address B
            )

# -----------------------------
# DRAW GRAPH
# -----------------------------
plt.figure(figsize=(12, 8))

pos = nx.spring_layout(cluster_graph, seed=42)

nx.draw(
    cluster_graph,
    pos,
    with_labels=False,
    node_size=500,
    alpha=0.8
)

plt.title("Multi-Input Address Cluster Graph")
plt.show()


small_clusters = build_input_clusters(df_inputs)
merged_clusters = merge_overlapping_sets(small_clusters)

# -----------------------------
# LOW ACTIVITY CHECK
# -----------------------------
if len(df_inputs) < 5 and len(merged_clusters) == 0:
    print("Low activity address — limited analysis available")

# continue with rest of analysis
addresses_to_expand = choose_addresses_to_expand(
    df_inputs,
    df_outputs,
    merged_clusters,
    seed_address,
    min_appearances=2
)


# -----------------------------
# 17. One-hop tracing
# -----------------------------

# Follow the money out of the cluster

# Step 1: get outgoing transactions from cluster
cluster_addresses = set(df_clusters["Address"])

cluster_spending_txs = df_inputs[
    df_inputs["Input Address"].isin(cluster_addresses)
]["Transaction ID"].unique()


# Step 2: get outputs of those transactions
cluster_outputs = df_outputs[
    df_outputs["Transaction ID"].isin(cluster_spending_txs)
]

# Step 3: exclude internal cluster addresses
external_outputs = cluster_outputs[
    ~cluster_outputs["Output Address"].isin(cluster_addresses)
]

# Step 4: rank where money went
summary = (
    external_outputs
    .groupby("Output Address")["Output Value"]
    .sum()
    .reset_index()
    .sort_values("Output Value", ascending=False)
    .reset_index(drop=True)
)

# Convert satoshis → BTC and round
summary["BTC"] = (summary["Output Value"] / 100_000_000).round(4)

# Show only BTC
print(summary[["Output Address", "BTC"]].head(10))


# Step 5: pick top 3–5 addresses after checking the output of previous steps


# -----------------------------
# 18. Follow the money - 1-hop expansion
# -----------------------------

# Step 1. Pick the top address
target = "1Q1ifiCyTtoYsrq2MQjZqpHSFREDTteE8E"

# Step 2. Fetch its transactions
txs_2 = get_all_transactions(target)

df_inputs_2 = build_transaction_inputs(txs_2)
df_outputs_2 = build_transaction_outputs(txs_2)


# -----------------------------
# 19. Separate 1-hop expansion graph
# -----------------------------

# This graph shows only the next-hop activity for the selected target address
# It keeps the visual separate from the original Locky seed graph

G_hop1 = nx.DiGraph()

# -----------------------------
# ADD INPUT EDGES
# -----------------------------
# These show addresses funding transactions involving the target address

for _, row in df_inputs_2.iterrows():
    G_hop1.add_edge(
        row["Input Address"],
        row["Transaction ID"],
        value=row["Input Value"],
        edge_type="input"
    )

# -----------------------------
# ADD OUTPUT EDGES
# -----------------------------
# These show transactions sending BTC to output addresses

for _, row in df_outputs_2.iterrows():
    G_hop1.add_edge(
        row["Transaction ID"],
        row["Output Address"],
        value=row["Output Value"],
        edge_type="output"
    )

# -----------------------------
# GRAPH LAYOUT
# -----------------------------
# Recalculate layout for this separate graph

plt.figure(figsize=(14, 10))

pos_hop1 = nx.spring_layout(
    G_hop1,
    k=0.5,
    seed=42
)

# -----------------------------
# NODE COLOURING
# -----------------------------
# Green = target address being traced
# Blue = other addresses
# Grey = transactions

node_colours_hop1 = []
node_sizes_hop1 = []

for node in G_hop1.nodes():
    if node == target:
        node_colours_hop1.append("green")      # traced 80 BTC address
        node_sizes_hop1.append(800)
    elif str(node).startswith(("1", "3", "bc1")):
        node_colours_hop1.append("lightblue")  # address nodes
        node_sizes_hop1.append(400)
    else:
        node_colours_hop1.append("lightgrey")  # transaction nodes
        node_sizes_hop1.append(250)

# -----------------------------
# DRAW GRAPH
# -----------------------------

nx.draw(
    G_hop1,
    pos_hop1,
    with_labels=False,
    node_size=node_sizes_hop1,
    node_color=node_colours_hop1,
    arrows=True,
    alpha=0.8
)

# -----------------------------
# ADD LEGEND
# -----------------------------

legend_handles_hop1 = [
    mpatches.Patch(color="green", label="Traced Address"),
    mpatches.Patch(color="lightblue", label="Address"),
    mpatches.Patch(color="lightgrey", label="Transaction")
]

plt.legend(handles=legend_handles_hop1)

plt.title("1-Hop Expansion from 80 BTC Output Address", pad=20)
plt.show()