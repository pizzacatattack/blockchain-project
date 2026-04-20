import requests
import pandas as pd
import time


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

