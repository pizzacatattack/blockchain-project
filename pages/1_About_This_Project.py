import streamlit as st

st.title("About This Project")

st.write("Bitcoin transactions are public, but that does not mean they are easy to understand.")
st.write("This student cyber security project uses blockchain data, visualisations and real-world case studies to make Bitcoin tracing concepts easier to explore.")

st.warning(
    "This app can highlight suspicious-looking transaction patterns, but it cannot confirm who owns a Bitcoin address or whether a crime has occurred."
)

st.header("What this project does")

st.markdown("""
This application was built to make Bitcoin tracing concepts easier to explore and explain.

It can help users:

- inspect Bitcoin addresses and transaction activity
- visualise how funds move between addresses and transactions
- explore real-world cybercrime case studies
- understand suspicious movement patterns such as batching, clustering and peel chains
- investigate transactions in a more structured and beginner-friendly way
""")

st.header("How the application works")

st.write(
    "This application uses publicly available Bitcoin blockchain data to explore how cryptocurrency transactions can be traced and interpreted."
)

st.markdown("""
**Data source**
- **Blockstream API** is used to retrieve live Bitcoin address and transaction data.

**Tools used**
- **Python** for data collection and processing
- **pandas** for transaction tables and summaries
- **NetworkX** for transaction graph modelling
- **Matplotlib** for visualisations
- **Streamlit** for the interactive application interface

**Tracing methods used**
This application uses practical blockchain tracing techniques, including:

- address-level transaction analysis
- transaction-level investigation
- graph-based visualisation of fund movement
- case-study-based tracing examples
- heuristic observation of patterns such as batching, clustering and peel-chain behaviour
""")

st.header("How to use the application")

st.markdown("""
**1. Start with a Bitcoin address**

Enter your own Bitcoin address, or use one of the sample addresses provided.

**2. Review the summary**

Check the address statistics, including received Bitcoin, spent Bitcoin, balance and transaction count.

**3. Investigate transactions**

Use the transaction tables to identify interesting transaction IDs.

**4. Inspect individual transactions**

Copy a transaction ID into the Transaction ID Explorer to view the full transaction breakdown.

**5. Explore the case studies**

Open the case study pages from the sidebar to see tracing techniques applied to real-world examples.
""")


st.header("Case studies included")

st.write(
    "The case studies are arranged to show how blockchain tracing becomes increasingly difficult as more advanced evasion techniques are introduced. "
    "The clustering case study shows how related Bitcoin addresses can sometimes be linked through transaction analysis. "
    "The later peel-chain and mixer case studies explore techniques designed to make suspicious fund movement harder to follow."
)

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Locky ransomware")
    st.write(
        "Explores transaction behaviour linked to a ransomware ecosystem and shows how blockchain analysis can help investigate suspicious wallet activity."
    )

with col2:
    st.subheader("Conti peel chain")
    st.write(
        "Explores a peel-chain style movement pattern, where funds move through a sequence of transactions while smaller amounts are separated along the way."
    )

with col3:
    st.subheader("ChipMixer / CoinJoin")
    st.write(
        "Explores batching, denomination splitting and transaction behaviours that may be associated with mixing-style activity."
    )

st.header("Important limitations")

st.markdown("""
Blockchain tracing has important limits.

- **Addresses are not people.** A Bitcoin address does not directly identify a person, company or criminal group.
- **Patterns are clues, not proof.** Some transaction behaviours may look suspicious, but they do not automatically mean criminal activity is taking place.
- **Some transactions combine funds from multiple addresses.** This can make it difficult to tell exactly how much came from one address.
- **Live data can vary.** Results may change depending on API availability, transaction history limits and network timing.
- **Not every unusual pattern is suspicious.** Legitimate cryptocurrency services can sometimes create transaction patterns that look similar to laundering activity.
""")

st.header("Future improvements")

st.markdown("""
Possible future improvements include:

- suspicious activity checker for user-entered address
- improved graph layouts for large transaction networks
- exportable investigation reports
- additional ransomware and hack case studies
- clearer guidance when analysing addresses with very little transaction activity
- better handling when live blockchain data is temporarily unavailable
            
""")

st.header("Development note")

st.write(
    "This student project was developed as an AI-assisted blockchain tracing application, with AI used as a development support tool for coding, implementation and debugging."
)