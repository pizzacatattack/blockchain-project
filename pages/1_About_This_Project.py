import streamlit as st

st.title("₿ About Blockchain Hide and Seek")

st.write(
    "Bitcoin transactions are public, but that does not mean they are easy to understand. "
    "This project was created to help beginners learn how to follow the money on the blockchain using real-world case studies, visualisations and hands-on investigation."
)

st.write(
    "Blockchain tracing is often described as a game of hide and seek. "
    "Users try to hide their activity, while investigators try to uncover patterns and follow the trail."
)

st.warning(
    "Patterns on the blockchain can point investigators in the right direction, but they are not proof. "
    "This application cannot confirm who owns an address or whether a transaction is linked to criminal activity."
)

st.header("What this project does")

st.markdown("""
The goal of this project is simple: help users feel confident enough to start following the money themselves:

- investigate Bitcoin addresses and transactions
- visualise how money moves through the blockchain
- learn foundational tracing techniques such as clustering and peel chains
- explore real-world ransomware, mixer and hack case studies
- identify transactions that do not pass the vibe check
""")

st.header("How the application works")

st.write(
    "The application retrieves live Bitcoin transaction data from the blockchain and presents it in a way that is easier to explore and understand."
)

st.markdown("""
**Tools used**
- Blockstream API to retrieve live Bitcoin transaction data
- Python to build the application logic
- pandas for transaction tables and summaries
- NetworkX for graph-based visualisations
- Matplotlib for charts and diagrams
- Streamlit to publish the application online
""")


st.subheader("Tracing methods used")

st.write(
    "Blockchain tracing is a bit like a game of hide and seek. This application introduces some of the techniques investigators use to uncover patterns and follow the money."
)

st.markdown("""
- tracking Bitcoin as it moves between addresses
- visualising transaction flows using graphs
- identifying possible address clusters
- spotting peel chains, batching behaviour and other transaction patterns
- exploring real-world ransomware, mixer and hack case studies
- learning which transactions pass the vibe check and which ones deserve a closer look
""")

st.header("How to use the application")

st.markdown("""
**1. Pick a trail to follow**

Enter a Bitcoin address or choose one of the sample case studies.

**2. Start asking questions**

Who is sending Bitcoin to this address? Where is the money going? Is there anything unusual about the activity?

**3. Follow the money**

Use the transaction tables to trace the movement of funds through the blockchain.

**4. Dig deeper**

Open individual transactions to see exactly which addresses were involved.

**5. Clock suspicious behaviour**

Look for patterns that do not pass the vibe check, such as clustering, peel chains or mixing activity.

**6. Put your skills to the test**

Explore the case studies and see if you can follow the money yourself.
""")

st.header("Case studies included")

st.write(
    "The case studies are arranged to show how the game of blockchain hide and seek evolves over time. "
    "The first case study focuses on clustering and demonstrates how investigators can use transaction patterns to link related addresses together. "
    "The later case studies explore peel chains and mixers, which are designed to make following the money much more difficult."
)
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Locky clustering")
    st.write(
        "Learn how clustering techniques can help investigators identify groups of addresses that may belong to the same entity."

    )

with col2:
    st.subheader("Conti peel chain")
    st.write(
        "Follow a suspected peel chain and see how criminals attempt to ghost their funds by repeatedly moving Bitcoin between addresses."
    )

with col3:
    st.subheader("ChipMixer")
    st.write(
        "Explore transaction structures associated with mixing activity and learn why mixers make blockchain tracing more difficult."
    )

st.header("Important limitations")

st.markdown("""
Blockchain tracing is a powerful tool, but it is not a crystal ball.

- **Addresses are not people.** A Bitcoin address does not directly identify a person, company or criminal group.
- **Patterns are clues, not proof.** The blockchain can point investigators in the right direction, but it does not provide all the answers.
- **Not every transaction passes the vibe check.** Some unusual-looking transactions have perfectly innocent explanations.
- **Some users are better at hide and seek than others.** Techniques such as mixers, peel chains and privacy-focused cryptocurrencies can make tracing more difficult.
- **Investigators use more than just the blockchain.** On-chain analysis is often combined with off-chain investigation techniques.
- **Live data changes over time.** The blockchain never sleeps, so results can change as new transactions occur.
""")

st.header("Future improvements")

st.markdown("""
Possible future improvements include:

- automatic "does this pass the vibe check?" scoring
- additional ransomware and hack case studies
- clearer visualisations showing how money moves
- improved handling of busy Bitcoin addresses with lots of transactions
- exportable investigation reports

            
""")

st.header("Development note")

st.write(
    "This student project was developed with assistance from OpenAI's ChatGPT."
)
st.write(
    "ChatGPT was used for coding, debugging, feature implementation, visualisation design, brainstorming, technical explanations and editing support."
)
st.divider()

st.caption(
    "Created by Shahera. Some transactions pass the vibe check. Some don't. Clock it!"
)