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

max_pages = st.slider("Max pages per query", 1, 5, 1)

def run_actor(q: str):
    payload = {
        # IMPORTANT: this actor expects queries as a STRING
        # Put one query per line if you want multiple queries.
        "queries": q,
        "maxPagesPerQuery": max_pages,
        "countryCode": "US",
        "languageCode": "en",
        "safeSearch": "off",
    }
    r = requests.post(RUN_ENDPOINT, params={"token": APIFY_TOKEN}, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()

if st.button("Run test"):
    try:
        with st.spinner("Running actor..."):
            items = run_actor(query)

        st.success(f"Success! Items returned: {len(items)}")
        st.subheader("Raw dataset items (first 3)")
        st.json(items[:3])

    except Exception as e:
        st.error("Apify request failed")
        st.exception(e)
