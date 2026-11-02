
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Supabase Database Test",
    layout="wide"
)

st.title("Pro Star Lizard — Database Test")

st.write("Checking our historical xG database...")

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SECRET_KEY"]

    supabase = create_client(url, key)

    response = (
        supabase.table("historical_xg")
        .select("*", count="exact")
        .limit(5)
        .execute()
    )

    st.success("Connected to Supabase successfully!")

    st.metric(
        "Historical matches stored",
        response.count
    )

    st.subheader("Sample historical matches")

    if response.data:
        st.dataframe(
            response.data,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("Database connected, but no matches found.")

except Exception as error:
    st.error("Database connection test failed.")
    st.code(str(error))
