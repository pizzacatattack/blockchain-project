import requests
import pandas as pd
import time
import networkx as nx
import matplotlib.pyplot as plt


# -----------------------------
# CONFIG
# -----------------------------

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)

case_name = "Chipmixer"

seed_address = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"

BRANCH_TOP_N = 3
BRANCH_MAX_HOPS = 3
BRANCH_MAX_PAGES_PER_ADDRESS = 2

MAX_HOPS = 15
GRAPH_STEPS = 6
MIN_BTC = 0.001


# -----------------------------
# Get all confirmed transactions for an address
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
            print(f"Reached max_pages={max_pages}. Stopping fetch.")
            break

        if len(data) < 25:
            break

        last_seen = data[-1]["txid"]
        time.sleep(0.5)

    return all_txs

# -----------------------------
# MIXER / COINJOIN DETECTION LOGIC
# -----------------------------

# These thresholds define what we consider "suspicious" or mixer-like behaviour
MIXER_MIN_INPUTS = 5              # CoinJoin tx usually have many participants (inputs)
MIXER_MIN_OUTPUTS = 5             # and many outputs
MIXER_MIN_EQUAL_OUTPUTS = 3       # multiple identical outputs is a key CoinJoin signal
VALUE_TOLERANCE_SATS = 1000       # allow tiny rounding differences (in satoshis)
FEE_OUTPUT_MAX_BTC = 0.01         # small outputs may represent coordinator fees


# -----------------------------
# Convert satoshis → BTC
# -----------------------------
def sats_to_btc(value):
    """
    Convert satoshis to BTC.
    Bitcoin API returns values in satoshis (1 BTC = 100,000,000 sats).
    """
    return value / 100_000_000 if value is not None else None


# -----------------------------
# Detect equal-sized output groups
# -----------------------------
def detect_equal_output_groups(tx, tolerance_sats=1000):
    """
    Identify groups of outputs that have roughly the same value.

    Why?
    - CoinJoin transactions deliberately create equal-sized outputs
      so it is difficult to link inputs to outputs.

    Returns:
        List of groups, where each group is a list of outputs
        with similar values.
    """

    outputs = []

    # Extract all outputs from the transaction
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
    used = set()  # track which outputs we've already grouped

    # Compare each output with every other output
    for i, output in enumerate(outputs):
        if i in used:
            continue

        group = [output]
        used.add(i)

        for j, other in enumerate(outputs):
            if j in used:
                continue

            # Check if values are "close enough" (within tolerance)
            if abs(output["value_sats"] - other["value_sats"]) <= tolerance_sats:
                group.append(other)
                used.add(j)

        # Only keep groups that are large enough to be meaningful
        if len(group) >= MIXER_MIN_EQUAL_OUTPUTS:
            groups.append(group)

    return groups


# -----------------------------
# Score a transaction for mixer-like behaviour
# -----------------------------
def score_mixer_transaction(tx):
    """
    Analyse a single transaction and assign a "mixer likelihood score".

    Higher score = more likely to be CoinJoin / mixer activity.

    We look at:
    - number of inputs
    - number of outputs
    - number of equal-sized outputs
    - number of unique addresses
    - presence of small "fee-like" outputs
    """

    txid = tx["txid"]
    timestamp = tx["status"].get("block_time")

    inputs = tx.get("vin", [])
    outputs = tx.get("vout", [])

    input_addresses = set()
    output_addresses = set()

    input_value = 0
    output_value = 0

    # -----------------------------
    # Process inputs
    # -----------------------------
    for vin in inputs:
        prevout = vin.get("prevout", {})
        address = prevout.get("scriptpubkey_address")
        value = prevout.get("value")

        if address:
            input_addresses.add(address)

        if value:
            input_value += value

    # -----------------------------
    # Process outputs
    # -----------------------------
    for vout in outputs:
        address = vout.get("scriptpubkey_address")
        value = vout.get("value")

        if address:
            output_addresses.add(address)

        if value:
            output_value += value

    # -----------------------------
    # Detect equal-sized outputs
    # -----------------------------
    equal_groups = detect_equal_output_groups(tx, VALUE_TOLERANCE_SATS)

    largest_equal_group_size = 0
    largest_equal_group_value = None

    if equal_groups:
        # Find the largest group of equal outputs
        largest_group = max(equal_groups, key=len)
        largest_equal_group_size = len(largest_group)
        largest_equal_group_value = largest_group[0]["value_btc"]

    # -----------------------------
    # Detect possible fee outputs
    # -----------------------------
    fee_outputs = []

    for vout in outputs:
        value = vout.get("value")
        address = vout.get("scriptpubkey_address")

        if value is None:
            continue

        btc = sats_to_btc(value)

        # Very small outputs often represent coordinator fees
        if btc <= FEE_OUTPUT_MAX_BTC:
            fee_outputs.append({
                "address": address,
                "value_btc": btc
            })

    # -----------------------------
    # Scoring logic
    # -----------------------------
    score = 0
    reasons = []

    if len(inputs) >= MIXER_MIN_INPUTS:
        score += 2
        reasons.append("many inputs")

    if len(outputs) >= MIXER_MIN_OUTPUTS:
        score += 2
        reasons.append("many outputs")

    if largest_equal_group_size >= MIXER_MIN_EQUAL_OUTPUTS:
        score += 3
        reasons.append("repeated equal-sized outputs")

    if len(input_addresses) >= 3:
        score += 1
        reasons.append("multiple input addresses")

    if len(output_addresses) >= 3:
        score += 1
        reasons.append("multiple output addresses")

    if len(fee_outputs) > 0:
        score += 1
        reasons.append("small possible fee/coordinator outputs")

    # -----------------------------
    # Return structured result
    # -----------------------------
    return {
        "Transaction ID": txid,
        "Timestamp": pd.to_datetime(timestamp, unit="s", errors="coerce"),
        "Input Count": len(inputs),
        "Output Count": len(outputs),
        "Unique Input Addresses": len(input_addresses),
        "Unique Output Addresses": len(output_addresses),
        "Input BTC": sats_to_btc(input_value),
        "Output BTC": sats_to_btc(output_value),
        "Estimated Fee BTC": sats_to_btc(input_value - output_value),
        "Largest Equal Output Group": largest_equal_group_size,
        "Equal Output BTC": largest_equal_group_value,
        "Possible Fee Outputs": len(fee_outputs),
        "Mixer Score": score,
        "Reasons": ", ".join(reasons)
    }


# -----------------------------
# Analyse all transactions for an address
# -----------------------------
def analyse_address_for_mixer_activity(address, max_pages=3):
    """
    Fetch transactions for an address and score each one.

    This is the main entry point for mixer detection.
    """

    print(f"\nAnalysing possible mixer activity for: {address}")

    txs = get_all_transactions(address, max_pages=max_pages)

    results = []

    for tx in txs:
        result = score_mixer_transaction(tx)
        results.append(result)

    mixer_df = pd.DataFrame(results)

    # Sort by most suspicious first
    mixer_df = mixer_df.sort_values(
        by=["Mixer Score", "Largest Equal Output Group"],
        ascending=False
    ).reset_index(drop=True)

    return mixer_df


# -----------------------------
# Print likely mixer transactions
# -----------------------------
def print_mixer_findings(mixer_df, min_score=5):
    """
    Display only transactions that exceed a given mixer score threshold.
    """

    likely = mixer_df[mixer_df["Mixer Score"] >= min_score]

    print("\n--- Possible Mixer / CoinJoin Transactions ---")

    if likely.empty:
        print("No strong mixer-like transactions detected.")
        return

    print(likely[[
        "Transaction ID",
        "Timestamp",
        "Input Count",
        "Output Count",
        "Largest Equal Output Group",
        "Equal Output BTC",
        "Possible Fee Outputs",
        "Mixer Score",
        "Reasons"
    ]])


# -----------------------------
# Inspect one high-scoring mixer transaction
# -----------------------------
def inspect_transaction_structure(tx):
    """
    Inspect one transaction in detail.

    This helps explain WHY a transaction was scored as mixer-like.
    It prints:
    - number of inputs
    - number of outputs
    - most common output values
    """

    txid = tx["txid"]
    inputs = tx.get("vin", [])
    outputs = tx.get("vout", [])

    print("\n--- Detailed Transaction Structure ---")
    print(f"Transaction ID: {txid}")
    print(f"Input count: {len(inputs)}")
    print(f"Output count: {len(outputs)}")

    output_values = []

    for vout in outputs:
        value = vout.get("value")

        if value is not None:
            output_values.append({
                "Output BTC": sats_to_btc(value)
            })

    df_values = pd.DataFrame(output_values)

    if df_values.empty:
        print("No output values found.")
        return

    print("\n--- Most Common Output Values ---")
    print(
        df_values["Output BTC"]
        .value_counts()
        .reset_index()
        .rename(columns={
            "index": "Output BTC",
            "Output BTC": "Count"
        })
        .head(10)
    )


# -----------------------------
# Plot equal-output group sizes
# -----------------------------
def plot_equal_output_groups(mixer_df):
    """
    Plot the distribution of equal-output group sizes.

    Large equal-output groups are a strong CoinJoin indicator.
    """

    if mixer_df.empty:
        print("No mixer data available to plot.")
        return

    plt.figure(figsize=(10, 6))

    mixer_df["Largest Equal Output Group"].hist(bins=20)

    plt.title("Largest Equal-Output Groups in Mixer-Like Transactions")
    plt.xlabel("Largest Equal-Output Group Size")
    plt.ylabel("Number of Transactions")

    plt.show()


# -----------------------------
# Compare two suspected mixer addresses
# -----------------------------
def compare_addresses(address_1, address_2, max_pages=5):
    """
    Compare mixer-like behaviour across two addresses.

    This is useful for your project because the paper mentions two addresses.
    One may be historical/inactive, while the other may show different behaviour.
    """

    print("\n=============================")
    print("COMPARING MIXER ADDRESSES")
    print("=============================")

    df1 = analyse_address_for_mixer_activity(address_1, max_pages=max_pages)
    df2 = analyse_address_for_mixer_activity(address_2, max_pages=max_pages)

    summary = pd.DataFrame([
        {
            "Address Label": "Address 1",
            "Address": address_1,
            "Transactions Analysed": len(df1),
            "Likely Mixer TX": len(df1[df1["Mixer Score"] >= 5]),
            "Highest Mixer Score": df1["Mixer Score"].max(),
            "Average Inputs": round(df1["Input Count"].mean(), 2),
            "Average Outputs": round(df1["Output Count"].mean(), 2),
            "Largest Equal-Output Group": df1["Largest Equal Output Group"].max()
        },
        {
            "Address Label": "Address 2",
            "Address": address_2,
            "Transactions Analysed": len(df2),
            "Likely Mixer TX": len(df2[df2["Mixer Score"] >= 5]),
            "Highest Mixer Score": df2["Mixer Score"].max(),
            "Average Inputs": round(df2["Input Count"].mean(), 2),
            "Average Outputs": round(df2["Output Count"].mean(), 2),
            "Largest Equal-Output Group": df2["Largest Equal Output Group"].max()
        }
    ])

    print("\n--- Address Comparison Summary ---")
    print(summary)

    return summary, df1, df2


# -----------------------------
# RUN MIXER ANALYSIS
# -----------------------------

print("\n=============================")
print("MIXER ANALYSIS STARTING")
print("=============================")

# Address from the paper
address_1 = "bc1qs604c7jv6amk4cxqlnvuxv26hv3e48cds4m0ew"

# Second address from the paper
address_2 = "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw"

# Use address_1 as the main case study address
seed_address = address_1

# Fetch and score transactions for the main address
txs = get_all_transactions(seed_address, max_pages=5)

results = []

for tx in txs:
    result = score_mixer_transaction(tx)
    results.append(result)

mixer_df = pd.DataFrame(results)

mixer_df = mixer_df.sort_values(
    by=["Mixer Score", "Largest Equal Output Group"],
    ascending=False
).reset_index(drop=True)

# Show only strong mixer-like transactions
print_mixer_findings(mixer_df, min_score=5)

# Show top results regardless
print("\n--- Top Scoring Transactions ---")
print(mixer_df.head(10))

# Summary statistics
print("\n--- Mixer Summary Statistics ---")
print(f"Transactions analysed: {len(mixer_df)}")
print(f"Likely mixer transactions: {len(mixer_df[mixer_df['Mixer Score'] >= 5])}")
print(f"Highest mixer score: {mixer_df['Mixer Score'].max()}")
print(f"Average input count: {round(mixer_df['Input Count'].mean(), 2)}")
print(f"Average output count: {round(mixer_df['Output Count'].mean(), 2)}")
print(f"Largest equal-output group: {mixer_df['Largest Equal Output Group'].max()}")

# Inspect the highest-scoring transaction in detail
print("\n=============================")
print("INSPECTING TOP MIXER-LIKE TRANSACTION")
print("=============================")

top_txid = mixer_df.iloc[0]["Transaction ID"]
top_tx = next(tx for tx in txs if tx["txid"] == top_txid)

inspect_transaction_structure(top_tx)

# Plot equal-output group sizes
print("\nOpening equal-output group histogram...")
plot_equal_output_groups(mixer_df)

# Compare both addresses from the paper
comparison_df, address_1_df, address_2_df = compare_addresses(
    address_1=address_1,
    address_2=address_2,
    max_pages=5
)