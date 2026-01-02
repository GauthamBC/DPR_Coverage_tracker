import requests
import streamlit as st

st.set_page_config(page_title="Apify Google Scraper Test", layout="wide")

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
RUN_ENDPOINT = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"

st.title("Apify Google Search Scraper — Output Preview")

query = st.text_input(
    "Query",
    value='("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com'
)

def run_actor(q: str):
    payload = {
        "queries": q,
        "maxPagesPerQuery": 1,
    }

    r = requests.post(RUN_ENDPOINT, params={"token": APIFY_TOKEN}, json=payload, timeout=120)

    if r.status_code >= 400:
        st.error(f"Apify returned {r.status_code}")
        try:
            st.json(r.json())
        except Exception:
            st.code(r.text)
        st.stop()

    return r.json()

if st.button("Run test"):
    items = run_actor(query)
    st.success(f"Success! Items returned: {len(items)}")
    st.json(items[:3])
