import requests
import streamlit as st

st.set_page_config(page_title="Apify Google Scraper Test", layout="wide")

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]

ACTOR_ENDPOINT = (
    "https://api.apify.com/v2/acts/"
    "apify~google-search-scraper/"
    "run-sync-get-dataset-items"
)

def run_actor():
    url = f"{ACTOR_ENDPOINT}?token={APIFY_TOKEN}"

    payload = {
        "queries": [
            {
                "query": '("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com'
            }
        ],
        "maxPagesPerQuery": 1,
        "countryCode": "US",
        "languageCode": "en",
        "safeSearch": "off",
    }

    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


st.title("Apify Google Search Scraper — Output Preview")

if st.button("Run test"):
    try:
        with st.spinner("Running actor..."):
            items = run_actor()

        st.success("Success! Results returned.")

        st.subheader("Raw dataset items (first 3)")
        st.json(items[:3])

        st.caption(f"Total items returned: {len(items)}")

    except Exception as e:
        st.error("Apify request failed")
        st.exception(e)
