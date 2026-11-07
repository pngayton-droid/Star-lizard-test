
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
    padding-top: 0.5rem;
    padding-bottom: 2rem;
    max-width: 1100px;
}

h1, h2, h3 {
    color: #f8fafc !important;
}

h2 {
    font-size: 1.65rem !important;
}

label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p {
    color: #e8eef8 !important;
    font-weight: 600 !important;
}

button[data-baseweb="tab"] {
    color: #e8eef8 !important;
    font-weight: 600 !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #ff6478 !important;
}

div[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #293a53;
    border-radius: 12px;
    padding: 12px;
}

@media (max-width: 640px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    h1 {
        font-size: 1.8rem !important;
    }

    h2 {
        font-size: 1.45rem !important;
    }

    div[data-testid="stTabs"] {
        font-size: 0.9rem;
    }
}
</style>
""", unsafe_allow_html=True)



st.image("pro_starlizard_header_correct-1.png", use_container_width=True)
  
  



if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

for page_name, page_icon in [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]:
    if st.button(
        f"{page_icon}  {page_name}",
        key=f"nav_{page_name}",
        use_container_width=True,
        type="primary" if st.session_state.active_page == page_name else "secondary",
    ):
        st.session_state.active_page = page_name

pricing = st.container() if st.session_state.active_page == "Match Pricing" else st.empty()
research = st.container() if st.session_state.active_page == "Historical Research" else st.empty()
database = st.container() if st.session_state.active_page == "Database Health" else st.empty()
  
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
