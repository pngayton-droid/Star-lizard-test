
import streamlit as st
from supabase import create_client

# ==========================================
# PRO STARLIZARD
# ==========================================

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# DARK MOBILE THEME
# ==========================================

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

label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p {
    color: #e8eef8 !important;
    font-weight: 600 !important;
}

div[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #293a53;
    border-radius: 12px;
    padding: 12px;
}

div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] *,
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    color: #f8fafc !important;
    opacity: 1 !important;
}

div.stButton > button {
    width: 100%;
    min-height: 3.2rem;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 700;
    border: 1px solid #41536c;
}

div.stButton > button[kind="primary"] {
    background-color: #b91c38;
    border-color: #ef4766;
    color: white;
}

div.stButton > button[kind="secondary"] {
    background-color: #172338;
    color: #f8fafc;
}

div.stButton > button p {
    color: inherit !important;
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
        font-size: 1.4rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# SCRUMPY AND LADY SALLY
# ==========================================

st.image(
    "pro_starlizard_header_correct-1.png",
    width="stretch",
)

# ==========================================
# SAFE ERROR DIAGNOSTICS
# ==========================================

def diagnose_error(error):
    """
    Return only a status code and safe category.
    Never display the raw exception message,
    request headers, URL or credentials.
    """

    status = getattr(error, "code", None)

    if status is None:
        status = getattr(error, "status_code", None)

    if isinstance(status, int):
        code = status

    elif (
        isinstance(status, str)
        and status.isdigit()
    ):
        code = int(status)

    else:
        code = None

    categories = {
        400: "Invalid request or database query",
        401: "Authentication rejected",
        403: "Permission denied",
        404: "Resource or table not found",
        406: "Response format rejected",
        408: "Request timed out",
        409: "Database conflict",
        422: "Request could not be processed",
        429: "Rate limit reached",
        500: "Server error",
        502: "Gateway error",
        503: "Service unavailable",
        504: "Gateway timeout",
    }

    if code is None:
        return {
            "type": type(error).__name__,
            "status": "Not provided",
            "category": "Further investigation required",
        }

    return {
        "type": type(error).__name__,
        "status": str(code),
        "category": categories.get(
            code,
            "Unclassified HTTP status",
        ),
    }


# ==========================================
# SUPABASE CONNECTION
# ==========================================

@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


# ==========================================
# DATABASE COUNTERS
# ==========================================

@st.cache_data(ttl=120, show_spinner=False)
def get_database_stats():

    results = {}
    errors = {}

    checks = [
        (
            "Historical xG records",
            "historical_xg",
            None,
            None,
        ),
        (
            "Match event records collected",
            "historical_match_events",
            None,
            None,
        ),
        (
            "Match statistics received",
            "historical_match_events",
            "stats_status",
            200,
        ),
        (
            "Goal/event timelines received",
            "historical_match_events",
            "timeline_status",
            200,
        ),
        (
            "Corners matched",
            "historical_match_events",
            "corners_match",
            True,
        ),
        (
            "Yellow cards matched",
            "historical_match_events",
            "yellow_cards_match",
            True,
        ),
        (
            "Red cards matched",
            "historical_match_events",
            "red_cards_match",
            True,
        ),
    ]

    try:
        db = get_supabase()

    except Exception as error:
        errors["Supabase connection"] = (
            diagnose_error(error)
        )

        return {
            "results": results,
            "errors": errors,
        }

    for label, table, column, value in checks:

        try:
            query = (
                db.table(table)
                .select(
                    "match_id",
                    count="exact",
                )
            )

            if column is not None:
                query = query.eq(column, value)

            response = query.limit(1).execute()

            results[label] = response.count

        except Exception as error:
            results[label] = None
            errors[label] = diagnose_error(error)

    return {
        "results": results,
        "errors": errors,
    }


# ==========================================
# NAVIGATION
# ==========================================

if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

pages = [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]

for page_name, page_icon in pages:

    selected = (
        st.session_state.active_page == page_name
    )

    if st.button(
        f"{page_icon}  {page_name}",
        key=f"nav_{page_name}",
        width="stretch",
        type="primary" if selected else "secondary",
    ):
        st.session_state.active_page = page_name
        st.rerun()

st.divider()

# ==========================================
# MATCH PRICING
# ==========================================

if st.session_state.active_page == "Match Pricing":

    st.header("Match Pricing")

    st.caption(
        "Pre-match and in-play football pricing terminal"
    )

    home = st.text_input(
        "Home team",
        placeholder="Enter home team",
    )

    away = st.text_input(
        "Away team",
        placeholder="Enter away team",
    )

    market = st.selectbox(
        "Select market",
        [
            "Match Goals",
            "Second-Half Goals",
            "Match Corners",
            "Second-Half Corners",
            "Cards",
            "Asian Handicap",
            "Asian Goal Totals",
            "Correct Score",
            "Next Goal",
            "Both Teams To Score",
        ],
    )

    st.info(
        "Pricing engine not connected yet. "
        "This is our dashboard preview."
    )

# ==========================================
# HISTORICAL RESEARCH
# ==========================================

elif st.session_state.active_page == "Historical Research":

    st.header("Historical Research")

    st.caption(
        "Investigate historical football statistics"
    )

    st.markdown("""
    **Research tools planned**
    - Historical expected goals (xG)
    - Halftime match situations
    - Second-half goal patterns
    - Goal and corner timings
    - Yellow and red cards
    - Referee research
    - Opposition-adjusted statistics
    - Backtesting and calibration
    """)

    st.info(
        "Historical research tools will be connected "
        "to our existing data."
    )

# ==========================================
# DATABASE HEALTH
# ==========================================

elif st.session_state.active_page == "Database Health":

    st.header("Database Health")

    st.caption(
        "Live historical collection statistics from Supabase"
    )

    if st.button(
        "🔄 Refresh database figures",
        width="stretch",
    ):
        get_database_stats.clear()

    with st.spinner("Checking database tables..."):
        data = get_database_stats()

    results = data["results"]
    errors = data["errors"]

    successful = sum(
        value is not None
        for value in results.values()
    )

    if successful == 7:
        st.success(
            "All seven database checks succeeded."
        )

    elif successful > 0:
        st.warning(
            f"{successful} of 7 database checks succeeded."
        )

    else:
        st.error(
            "No database counters could be retrieved."
        )

    st.subheader("Historical Database")

    for label in [
        "Historical xG records",
        "Match event records collected",
    ]:
        value = results.get(label)

        st.metric(
            label,
            f"{value:,}"
            if value is not None
            else "Unavailable",
        )

    st.subheader("Collection Status")

    for label in [
        "Match statistics received",
        "Goal/event timelines received",
    ]:
        value = results.get(label)

        st.metric(
            label,
            f"{value:,}"
            if value is not None
            else "Unavailable",
        )

    st.subheader("Verified Markets")

    for label in [
        "Corners matched",
        "Yellow cards matched",
        "Red cards matched",
    ]:
        value = results.get(label)

        st.metric(
            label,
            f"{value:,}"
            if value is not None
            else "Unavailable",
        )

    total = results.get(
        "Match event records collected"
    )

    verified = results.get(
        "Corners matched"
    )

    if (
        total is not None
        and verified is not None
        and total > 0
    ):
        st.metric(
            "Corner verification rate",
            f"{100 * verified / total:.1f}%",
        )

    # ======================================
    # DIAGNOSTICS
    # ======================================

    st.subheader("Database Diagnostics")

    if errors:

        st.warning(
            "Diagnostic results below show HTTP "
            "status codes where available. "
            "Credentials and raw error messages "
            "are deliberately hidden."
        )

        for label, details in errors.items():

            st.error(
                f"{label}\n\n"
                f"Error type: {details['type']}\n\n"
                f"HTTP status: {details['status']}\n\n"
                f"Category: {details['category']}"
            )

    else:
        st.success(
            "No database query errors detected."
        )

    st.caption(
        "This dashboard reads data only. "
        "It cannot modify or delete records."
    )

    st.caption(
        "Figures are cached for two minutes. "
        "Use Refresh to request current totals."
    )

# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "PRO STARLIZARD | Research and model estimates only. "
    "No automated betting."
)

st.caption(
    "🦎 Scrumpy & Lady Sally — Data Acquisition Team"
)
