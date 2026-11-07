
import streamlit as st

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp {
    background-color: #0b1220;
    color: #e8eef8;
}
.block-container {
    padding-top: 1.5rem;
    max-width: 1250px;
}
h1, h2, h3 {
    color: #f8fafc !important;
}
div[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #293a53;
    border-radius: 12px;
    padding: 16px;
}
div.stButton > button {
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)


st.image("pro_starlizard_header_correct.png", use_container_width=True)
  
st.caption("Professional Football Intelligence & Pricing")

st.markdown(
    "Goals • Corners • Cards • Asian Markets • Historical Research"
)

st.divider()

pricing, research, database = st.tabs([
    "⚽ Match Pricing",
    "📊 Historical Research",
    "🗄️ Database Health",
])

with pricing:
    st.header("Match Pricing")
    st.caption("Our future live and pre-match pricing terminal.")

    home = st.text_input("Home team", placeholder="Home team")
    away = st.text_input("Away team", placeholder="Away team")

    market = st.selectbox(
        "Market",
        [
            "Match Goals",
            "Second-Half Goals",
            "Match Corners",
            "Second-Half Corners",
            "Cards",
            "Asian Handicap",
            "Correct Score",
            "Next Goal",
        ],
    )

    st.info(
        "Pricing engine not connected yet. "
        "This is our new interface preview."
    )

with research:
    st.header("Historical Research")
    st.caption("Investigate historical patterns and match situations.")

    st.markdown("""
    **Planned research tools**

    - Historical xG and match results
    - Halftime situation analysis
    - Goal and corner timing
    - Cards and referee research
    - Opposition-adjusted statistics
    - Model backtesting and calibration
    """)

    st.info("Historical database connection coming next.")

with database:
    st.header("Database Health")
    st.caption("Monitor our Supabase historical data collection.")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Matches collected", "—")
    with c2:
        st.metric("Verified goals", "—")
    with c3:
        st.metric("Verified corners", "—")

    st.info(
        "Live database totals will appear here "
        "after we connect Supabase."
    )

st.divider()

st.caption(
    "PRO STARLIZARD | Research and model estimates only. "
    "No automated betting."
)

st.caption("🦎 Scrumpy & Lady Sally — Data Acquisition Team")
