import requests
import pandas as pd
import time
import matplotlib.pyplot as plt


# -----------------------------
# CONFIG
# -----------------------------

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 90)

case_name = "Binance Hack Motivating Example"

KNOWN_HACK_TXID = "e8b406091959700dbffcff30a60b190133721e5c39e89bb5fe23c5a554ab05ea"

MIN_OUTPUT_BTC = 0.01
MAX_PAGES_PER_ADDRESS = 3


# -----------------------------
# Helper: convert satoshis to BTC
# -----------------------------

def sats_to_btc(value):
    """
    Convert satoshis to BTC.
    Blockstream returns Bitcoin values in satoshis.
    """
    return value / 100_000_000 if value is not None else None


# -----------------------------
# Fetch one transaction by TXID
# -----------------------------

def get_transaction(txid):
    """
    Fetch a single Bitcoin transaction from the Blockstream API.
    """

    url = f"https://blockstream.info/api/tx/{txid}"

    res = requests.get(url, timeout=20)
    res.raise_for_status()

    return res.json()


# -----------------------------
# Fetch confirmed transactions for an address
# -----------------------------

def get_all_transactions(address, max_pages=None):
    """
    Fetch confirmed transactions involving an address.

    max_pages limits how many pages are fetched so the script
    does not run forever.
    """

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
            print("Could not fetch more transactions. Stopping.")
            break

        print(f"Fetched {len(data)} transactions for {address}")
        all_txs.extend(data)

        page_count += 1

        if max_pages is not None and page_count >= max_pages:
            break

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.5)

    return all_txs


# -----------------------------
# Extract outputs from one transaction
# -----------------------------

def extract_transaction_outputs(tx):
    """
    Convert one transaction's outputs into a readable table.

    Used for the original Binance hack transaction.
    """

    rows = []

    txid = tx["txid"]
    timestamp = tx["status"].get("block_time")

    for i, vout in enumerate(tx.get("vout", [])):
        value_sats = vout.get("value")
        address = vout.get("scriptpubkey_address")

        rows.append({
            "Transaction ID": txid,
            "Timestamp": pd.to_datetime(timestamp, unit="s", errors="coerce"),
            "Output Index": i,
            "Output Address": address,
            "Output BTC": sats_to_btc(value_sats)
        })

    df = pd.DataFrame(rows)

    return df.sort_values("Output BTC", ascending=False).reset_index(drop=True)


# -----------------------------
# Build outputs table from many transactions
# -----------------------------

def build_transaction_outputs(txs):
    """
    Convert many transactions into an outputs table.

    Used when following an address after the hack transaction.
    """

    rows = []

    for tx in txs:
        txid = tx["txid"]
        timestamp = tx["status"].get("block_time")

        for vout in tx.get("vout", []):
            address = vout.get("scriptpubkey_address")
            value = vout.get("value")

            if address is None or value is None:
                continue

            rows.append({
                "Transaction ID": txid,
                "Timestamp": pd.to_datetime(timestamp, unit="s", errors="coerce"),
                "Output Address": address,
                "BTC": sats_to_btc(value)
            })

    return pd.DataFrame(rows)


# -----------------------------
# Summarise outputs by address
# -----------------------------

def summarise_outputs(df_outputs):
    """
    Summarise total BTC received by each output address.
    """

    if df_outputs.empty:
        return df_outputs

    summary = (
        df_outputs
        .groupby("Output Address", as_index=False)
        .agg({"BTC": "sum"})
        .sort_values("BTC", ascending=False)
        .reset_index(drop=True)
    )

    return summary


# -----------------------------
# Detect equal-output groups
# -----------------------------

def detect_equal_output_groups(tx, tolerance_sats=1000, min_group_size=3):
    """
    Detect groups of outputs with the same or near-same value.

    CoinJoin transactions often have many equal-value outputs.
    """

    outputs = []

    for vout in tx.get("vout", []):
        value = vout.get("value")
        address = vout.get("scriptpubkey_address")

        if value is not None and address is not None:
            outputs.append({
                "address": address,
                "value_sats": value,
                "value_btc": sats_to_btc(value)
            })

    groups = []
    used = set()

    for i, output in enumerate(outputs):
        if i in used:
            continue

        group = [output]
        used.add(i)

        for j, other in enumerate(outputs):
            if j in used:
                continue

            if abs(output["value_sats"] - other["value_sats"]) <= tolerance_sats:
                group.append(other)
                used.add(j)

        if len(group) >= min_group_size:
            groups.append(group)

    return groups


# -----------------------------
# Score transaction for mixer-like structure
# -----------------------------

def score_mixer_transaction(tx):
    """
    Score a transaction based on mixer/CoinJoin-like structure.

    Higher score = more mixer-like.
    """

    inputs = tx.get("vin", [])
    outputs = tx.get("vout", [])

    input_addresses = set()
    output_addresses = set()

    for vin in inputs:
        prevout = vin.get("prevout", {})
        address = prevout.get("scriptpubkey_address")

        if address:
            input_addresses.add(address)

    for vout in outputs:
        address = vout.get("scriptpubkey_address")

        if address:
            output_addresses.add(address)

    equal_groups = detect_equal_output_groups(tx)

    largest_equal_group = 0

    if equal_groups:
        largest_equal_group = max(len(group) for group in equal_groups)

    score = 0
    reasons = []

    if len(inputs) >= 5:
        score += 2
        reasons.append("many inputs")

    if len(outputs) >= 5:
        score += 2
        reasons.append("many outputs")

    if largest_equal_group >= 3:
        score += 3
        reasons.append("repeated equal-sized outputs")

    if len(input_addresses) >= 3:
        score += 1
        reasons.append("multiple input addresses")

    if len(output_addresses) >= 3:
        score += 1
        reasons.append("multiple output addresses")

    return {
        "Transaction ID": tx["txid"],
        "Timestamp": pd.to_datetime(tx["status"].get("block_time"), unit="s", errors="coerce"),
        "Input Count": len(inputs),
        "Output Count": len(outputs),
        "Unique Input Addresses": len(input_addresses),
        "Unique Output Addresses": len(output_addresses),
        "Largest Equal Output Group": largest_equal_group,
        "Mixer Score": score,
        "Reasons": ", ".join(reasons)
    }


# -----------------------------
# Analyse downstream mixer-like activity
# -----------------------------

def analyse_address_after_hack(address):
    """
    For one output address from the hack transaction:
    - fetch later transactions involving that address
    - score those transactions for mixer-like behaviour
    """

    print(f"\nAnalysing downstream activity for address: {address}")

    txs = get_all_transactions(address, max_pages=MAX_PAGES_PER_ADDRESS)

    results = []

    for tx in txs:
        results.append(score_mixer_transaction(tx))

    df = pd.DataFrame(results)

    if df.empty:
        return df

    df = df.sort_values(
        by=["Mixer Score", "Largest Equal Output Group"],
        ascending=False
    ).reset_index(drop=True)

    return df


# -----------------------------
# Plot largest hack transaction outputs
# -----------------------------

def plot_hack_outputs(outputs_df):
    """
    Plot the largest direct outputs from the hack transaction.
    """

    top_outputs = outputs_df.head(10).copy()

    plt.figure(figsize=(12, 6))

    plt.bar(
        top_outputs["Output Address"].astype(str).str[:12],
        top_outputs["Output BTC"]
    )

    plt.title("Largest Outputs from Known Hack Transaction")
    plt.xlabel("Output Address, shortened")
    plt.ylabel("BTC")

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


# -----------------------------
# Follow one large hack output
# -----------------------------

def follow_hack_output_multi(address, max_hops=2, top_n=2, min_btc=0.01):
    """
    Follow one hack output, but allow limited branching.

    - max_hops: how deep to go
    - top_n: how many outputs to follow per hop
    """

    current_addresses = [address]

    print("\n=============================")
    print("FOLLOWING HACK OUTPUT (LIMITED BRANCHING)")
    print("=============================")

    for hop in range(1, max_hops + 1):
        print(f"\n--- Hop {hop} ---")

        next_addresses = []

        for addr in current_addresses:
            print(f"\nAddress: {addr}")

            txs = get_all_transactions(addr, max_pages=2)

            df_outputs = build_transaction_outputs(txs)
            summary = summarise_outputs(df_outputs)

            filtered = summary[
                (summary["BTC"] >= min_btc) &
                (summary["Output Address"] != addr)
            ].reset_index(drop=True)

            if filtered.empty:
                print("No meaningful outputs.")
                continue

            print(f"Number of outputs above threshold: {len(filtered)}")
            print(filtered.head(5))

            # Take top N outputs
            top_outputs = filtered.head(top_n)

            for _, row in top_outputs.iterrows():
                next_addresses.append(row["Output Address"])

                print(
                    f"Following candidate: {row['Output Address']} "
                    f"({round(row['BTC'], 4)} BTC)"
                )

            # Interpretation
            if len(filtered) > 5:
                print("Interpretation: heavy distribution stage.")
            elif len(filtered) <= 3:
                print("Interpretation: limited branching.")
            else:
                print("Interpretation: moderate distribution.")

        # Move to next hop
        current_addresses = next_addresses

        if not current_addresses:
            print("No further paths to follow.")
            break


# -----------------------------
# RUN BINANCE HACK MOTIVATING EXAMPLE
# -----------------------------

print("\n=============================")
print("BINANCE HACK MOTIVATING EXAMPLE")
print("=============================")

# Fetch the known hack transaction
hack_tx = get_transaction(KNOWN_HACK_TXID)

# Extract direct outputs from the hack transaction
outputs_df = extract_transaction_outputs(hack_tx)

print("\n--- Direct Outputs from Known Hack Transaction ---")
print(outputs_df)


# -----------------------------
# Hack transaction summary
# -----------------------------

total_btc = outputs_df["Output BTC"].sum()
num_outputs = len(outputs_df)

print("\n--- Hack Transaction Summary ---")
print(f"Total BTC distributed: {round(total_btc, 4)} BTC")
print(f"Number of outputs: {num_outputs}")
print(f"Average output size: {round(outputs_df['Output BTC'].mean(), 4)} BTC")
print(f"Largest output: {round(outputs_df['Output BTC'].max(), 4)} BTC")
print(f"Smallest output: {round(outputs_df['Output BTC'].min(), 8)} BTC")


# -----------------------------
# Filter meaningful outputs
# -----------------------------

large_outputs = outputs_df[
    outputs_df["Output BTC"] >= MIN_OUTPUT_BTC
].reset_index(drop=True)

print(f"\n--- Outputs Over {MIN_OUTPUT_BTC} BTC ---")
print(large_outputs)


# -----------------------------
# Plot largest outputs
# -----------------------------

plot_hack_outputs(outputs_df)


# -----------------------------
# Downstream mixer-like activity check
# -----------------------------

print("\n=============================")
print("DOWNSTREAM MIXER-LIKE ACTIVITY CHECK")
print("=============================")

downstream_results = []

for _, row in large_outputs.head(5).iterrows():
    address = row["Output Address"]

    if pd.isna(address):
        continue

    df = analyse_address_after_hack(address)

    if df.empty:
        continue

    best = df.iloc[0]

    downstream_results.append({
        "Hack Output Address": address,
        "Hack Output BTC": row["Output BTC"],
        "Best Downstream TX": best["Transaction ID"],
        "Best Mixer Score": best["Mixer Score"],
        "Largest Equal Output Group": best["Largest Equal Output Group"],
        "Reasons": best["Reasons"]
    })

downstream_df = pd.DataFrame(downstream_results)

print("\n--- Downstream Mixer-Like Summary ---")

if downstream_df.empty:
    print("No downstream mixer-like activity found in the limited search.")
else:
    print(downstream_df)

# -----------------------------
# Follow the largest direct output
# -----------------------------

largest_output_address = outputs_df.iloc[0]["Output Address"]

follow_hack_output_multi(
    address=largest_output_address,
    max_hops=2,
    top_n=2,
    min_btc=MIN_OUTPUT_BTC
)


# -----------------------------
# EXTRA: follow high-value recombined address
# -----------------------------

print("\n=============================")
print("FOLLOWING RECOMBINED 1000+ BTC ADDRESS")
print("=============================")

follow_hack_output_multi(
    address="bc1q2rdpyt8ed9pm56u9t0zjf94zrdu6gufa47pf62",
    max_hops=1,
    top_n=2,
    min_btc=MIN_OUTPUT_BTC
)