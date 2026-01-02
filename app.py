import requests
import pandas as pd
import streamlit as st
from datetime import date

st.set_page_config(page_title="DPR Coverage Tracker (Preview)", layout="wide")

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
RUN_ENDPOINT = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"

st.title("DPR Coverage Tracker — Preview")

# --- Inputs
queries_text = st.text_area(
    "Queries (one per line)",
    value='("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com',
    height=120,
)

colA, colB, colC = st.columns(3)
with colA:
    max_pages = st.slider("Max pages per query", 1, 5, 1)
with colB:
    country_code = st.text_input("Country code", "US")
with colC:
    exclude_actionnetwork_org = st.checkbox("Exclude actionnetwork.org results", value=True)

date_mode = st.selectbox(
    "Date range",
    ["Any time", "Last 24 hours", "Last 48 hours", "Last 7 days", "Last 30 days", "Last 12 months", "Custom range"],
    index=0,
)

after_date = None
before_date = None
quick_date_range = None

if date_mode == "Last 24 hours":
    quick_date_range = "h24"
elif date_mode == "Last 48 hours":
    quick_date_range = "h48"
elif date_mode == "Last 7 days":
    quick_date_range = "d7"
elif date_mode == "Last 30 days":
    quick_date_range = "d30"
elif date_mode == "Last 12 months":
    quick_date_range = "y1"
elif date_mode == "Custom range":
    c1, c2 = st.columns(2)
    with c1:
        after_date = st.date_input("After date (start)", value=date.today())
    with c2:
        before_date = st.date_input("Before date (end)", value=date.today())
    if after_date and before_date and after_date > before_date:
        st.warning("Start date must be on or before end date.")

run_btn = st.button("Run search")

# --- Helpers
def run_actor():
    payload = {
        # IMPORTANT: this actor expects queries as a STRING (one per line)
        "queries": queries_text,
        "maxPagesPerQuery": max_pages,
        "countryCode": country_code.strip().upper() if country_code else "US",
    }

    # Date filters supported by this actor:
    # - quickDateRange (h24, d7, m1, y1, etc.)
    # - afterDate / beforeDate (YYYY-MM-DD or relative like "8 days")
    if quick_date_range:
        payload["quickDateRange"] = quick_date_range
    if date_mode == "Custom range" and after_date and before_date and after_date <= before_date:
        payload["afterDate"] = after_date.strftime("%Y-%m-%d")
        payload["beforeDate"] = before_date.strftime("%Y-%m-%d")

    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}  # recommended auth style
    r = requests.post(RUN_ENDPOINT, headers=headers, json=payload, timeout=180)

    if r.status_code >= 400:
        # show the real Apify error body
        try:
            return None, r.status_code, r.json()
        except Exception:
            return None, r.status_code, r.text

    return r.json(), None, None


def flatten(items):
    rows = []
    for item in items:
        term = (item.get("searchQuery") or {}).get("term") or ""
        organic = item.get("organicResults") or []
        for r in organic:
            rows.append(
                {
                    "query": term,
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "displayedUrl": r.get("displayedUrl"),
                    "description": r.get("description"),
                    "date": r.get("date"),
                    "position": r.get("position"),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["url"] = df["url"].astype(str)
    df = df.dropna(subset=["url"]).drop_duplicates(subset=["url"])

    if exclude_actionnetwork_org:
        df = df[~df["url"].str.contains(r"actionnetwork\.org", case=False, na=False)]

    return df


# --- Run + Preview
if run_btn:
    with st.spinner("Running Apify actor..."):
        items, err_code, err_body = run_actor()

    if err_code:
        st.error(f"Apify error ({err_code})")
        st.json(err_body) if isinstance(err_body, dict) else st.code(str(err_body))
        st.stop()

    st.success(f"Returned {len(items)} SERP page(s).")

    df = flatten(items)
    st.subheader("Preview (Organic Results)")
    if df.empty:
        st.warning("No organic results found (or everything was filtered out).")
    else:
        st.dataframe(df, use_container_width=True)
        st.caption(f"Rows: {len(df)}")

    with st.expander("Raw JSON (first item)"):
        st.json(items[0] if items else {})
