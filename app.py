import requests
import streamlit as st

st.set_page_config(page_title="Apify Debug", layout="wide")

# Change this string anytime you redeploy so you KNOW you're seeing the latest code
BUILD_ID = "debug-v1"

APIFY_TOKEN = st.secrets.get("APIFY_TOKEN", "")

ACTOR_BASE = "https://api.apify.com/v2/acts/apify~google-search-scraper"
RUN_ENDPOINT = f"{ACTOR_BASE}/run-sync-get-dataset-items"

st.title("Apify Debug")
st.write("BUILD:", BUILD_ID)

# Never print the token itself. Print only safe info.
st.write("Token loaded:", bool(APIFY_TOKEN))
st.write("Token prefix ok:", APIFY_TOKEN.startswith("apify_api_"))
st.write("Token length:", len(APIFY_TOKEN))

st.subheader("Endpoints (no token shown)")
st.code(ACTOR_BASE)
st.code(RUN_ENDPOINT)

def get_actor():
    # This should return actor JSON if token+endpoint are good
    r = requests.get(ACTOR_BASE, params={"token": APIFY_TOKEN}, timeout=60)
    return r.status_code, r.text

def run_actor():
    payload = {
        "queries": [
            {"query": '("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com'}
        ],
        "maxPagesPerQuery": 1,
        "countryCode": "US",
        "languageCode": "en",
        "safeSearch": "off",
    }
    r = requests.post(RUN_ENDPOINT, params={"token": APIFY_TOKEN}, json=payload, timeout=120)
    return r.status_code, r.text

col1, col2 = st.columns(2)

with col1:
    if st.button("1) Test GET Actor"):
        status, text = get_actor()
        st.write("Status:", status)
        st.code(text)

with col2:
    if st.button("2) Test Run (sync dataset items)"):
        status, text = run_actor()
        st.write("Status:", status)
        st.code(text)
