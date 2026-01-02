import requests
import pandas as pd
import streamlit as st
from datetime import date

st.set_page_config(page_title="DPR Coverage Tracker (Preview)", layout="wide")

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
RUN_ENDPOINT = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"

st.title("DPR Coverage Tracker — Preview")

# --------------------
# UI: Inputs
# --------------------
queries_text = st.text_area(
    "Queries (one per line)",
    value='("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com',
    height=120,
)

c1, c2, c3 = st.columns(3)
with c1:
    max_pages = st.slider("Max pages per query", 1, 5, 1)
with c2:
    # IMPORTANT: Apify expects lowercase country codes like "us", "gb", "ie"
    country_code = st.selectbox("Country", ["us", "gb", "ie", "ca", "au", ""], index=0)
with c3:
    exclude_actionnetwork_org = st.checkbox("Exclude actionnetwork.org results", value=True)

date_mode = st.selectbox(
    "Date range",
    ["Any time", "Last 24 hours", "Last 48 hours", "Last 7 days", "Last 30 days", "Last 12 months", "Custom range"],
    index=0,
)

after_date = None
before_date = None
quick_date_range = None

# Map UI to Apify actor fields (supported by this actor)
# quickDateRange examples commonly supported: h24, h48, d7, d30, y1
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
    cc1, cc2 = st.columns(2)
    with cc1:
        after_date = st.date_input("Start date", value=date.today())
    with cc2:
        before_date = st.date_input("End date", value=date.today())
    if after_date and before_date and after_date > before_date:
        st.warning("Start date must be on or before end date.")

run_btn = st.button("Run search")

# --------------------
# Helpers
# --------------------
def run_actor():
    payload = {
        # Actor expects queries as a STRING (one per line)
        "queries": queries_text,
        "maxPagesPerQuery": max_pages,
    }

    # Only include countryCode if set ("" means default)
    if country_code != "":
        payload["countryCode"] = country_code  # already lowercase from selectbox

    # Date filters
    if quick_date_range:
        payload["quickDateRange"] = quick_date_range
    if date_mode == "Custom range" and after_date and before_date and after_date <= before_date:
        payload["afterDate"] = after_date.strftime("%Y-%m-%d")
        payload["beforeDate"] = before_date.strftime("%Y-%m-%d")

    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    r = requests.post(RUN_ENDPOINT, headers=headers, json=payload, timeout=180)

    if r.status_code >= 400:
        try:
            return None, r.status_code, r.json()
        except Exception:
            return None, r.status_code, r.text

    return r.json(), None, None


def flatten(items):
    """
    Flattens Apify output like you posted:
    items[i].searchQuery.term
    items[i].organicResults[]
    """
    rows = []
    for item in items or []:
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
                    "type": r.get("type"),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["url"] = df["url"].astype(str)
    df = df.dropna(subset=["url"]).drop_duplicates(subset=["url"])

    if exclude_actionnetwork_org:
        df = df[~df["url"].str.contains(r"actionnetwork\.org", case=False, na=False)]

    # Optional: basic “likely PR-ish” tag
    kw = ["new study", "survey", "report", "findings", "new research", "announced", "press release"]
    df["likely_pr"] = df["description"].fillna("").str.lower().apply(lambda s: any(k in s for k in kw))

    # Nice column order
    cols = ["likely_pr", "query", "title", "date", "position", "url", "displayedUrl", "description"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


# --------------------
# Run + Preview
# --------------------
if run_btn:
    with st.spinner("Running Apify actor..."):
        items, err_code, err_body = run_actor()

    if err_code:
        st.error(f"Apify error ({err_code})")
        if isinstance(err_body, dict):
            st.json(err_body)
        else:
            st.code(str(err_body))
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
