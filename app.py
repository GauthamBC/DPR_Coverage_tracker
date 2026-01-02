import urllib.parse
import requests
import pandas as pd
import streamlit as st
from datetime import date, timedelta

st.set_page_config(page_title="Apify Google Scraper Test", layout="wide")

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
ACTOR_ID = st.secrets.get("APIFY_ACTOR_ID", "apify/google-search-scraper")


def build_tbs(preset: str, start: date | None = None, end: date | None = None) -> str | None:
    preset = preset.strip().lower()
    today = date.today()

    if preset == "any time":
        return None
    if preset == "last 24 hours":
        return "qdr:d"
    if preset == "last 48 hours":
        # Approx via custom date window (last 2 days)
        start = today - timedelta(days=2)
        end = today
        return f"cdr:1,cd_min:{start.strftime('%m/%d/%Y')},cd_max:{end.strftime('%m/%d/%Y')}"
    if preset == "last 7 days":
        return "qdr:w"
    if preset == "last 30 days":
        return "qdr:m"
    if preset == "last 12 months":
        return "qdr:y"
    if preset == "custom range":
        if not start or not end:
            return None
        return f"cdr:1,cd_min:{start.strftime('%m/%d/%Y')},cd_max:{end.strftime('%m/%d/%Y')}"
    return None


def run_actor_and_get_items(
    queries,
    max_pages_per_query=1,
    country_code="US",
    language_code="en",
    safe_search="active",
    wait_for_finish=120,
    limit_items=200,
    tbs: str | None = None,
):
    run_url = f"https://api.apify.com/v2/acts/{urllib.parse.quote(ACTOR_ID)}/runs"
    params = {"token": APIFY_TOKEN, "waitForFinish": wait_for_finish}

    # NOTE: Actor schemas can vary. We pass tbs as a top-level input field (if supported).
    payload = {
        "queries": [{"query": q} for q in queries],
        "maxPagesPerQuery": max_pages_per_query,
        "countryCode": country_code,
        "languageCode": language_code,
        "safeSearch": safe_search,
    }
    if tbs:
        payload["tbs"] = tbs

    r = requests.post(run_url, params=params, json=payload, timeout=wait_for_finish + 30)
    r.raise_for_status()
    run = r.json()["data"]

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("No defaultDatasetId returned from run.")

    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    items_params = {"token": APIFY_TOKEN, "clean": "true", "limit": limit_items}
    items_resp = requests.get(items_url, params=items_params, timeout=60)
    items_resp.raise_for_status()
    items = items_resp.json()

    return run, items


def flatten_organic(items):
    rows = []
    for it in items:
        query = it.get("query") or it.get("searchQuery") or it.get("search") or ""
        organic = it.get("organicResults") or it.get("organic_results") or []

        if isinstance(organic, list) and organic:
            for r in organic:
                rows.append(
                    {
                        "query": query,
                        "title": r.get("title"),
                        "link": r.get("url") or r.get("link"),
                        "snippet": r.get("snippet") or r.get("description"),
                        "source": r.get("source"),
                        "date": r.get("date"),
                    }
                )
        else:
            link = it.get("url") or it.get("link")
            if link:
                rows.append(
                    {
                        "query": query,
                        "title": it.get("title"),
                        "link": link,
                        "snippet": it.get("snippet") or it.get("description"),
                        "source": it.get("source"),
                        "date": it.get("date"),
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.dropna(subset=["link"])
    df["link"] = df["link"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["link"])
    return df


st.title("Apify Google Search Scraper — Output Preview")

with st.sidebar:
    st.header("Search settings")

    default_query = '("Action Network") ("new study" OR survey OR report OR findings) -site:actionnetwork.com'
    raw_queries = st.text_area("Queries (one per line)", value=default_query, height=120)

    max_pages = st.slider("Max pages per query", 1, 5, 1)
    country = st.text_input("Country code", "US")
    lang = st.text_input("Language code", "en")
    safe = st.selectbox("SafeSearch", ["active", "off"], index=0)
    limit_items = st.slider("Max items fetched", 50, 1000, 200, step=50)

    st.divider()
    st.header("Date range")

    preset = st.selectbox(
        "Recency",
        ["Any time", "Last 24 hours", "Last 48 hours", "Last 7 days", "Last 30 days", "Last 12 months", "Custom range"],
        index=1,
    )

    start_date = end_date = None
    if preset == "Custom range":
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=date.today())
        with c2:
            end_date = st.date_input("End date", value=date.today())

    run_btn = st.button("Run test")


if run_btn:
    queries = [q.strip() for q in raw_queries.splitlines() if q.strip()]
    if not queries:
        st.error("Please enter at least one query.")
        st.stop()

    tbs = build_tbs(preset, start=start_date, end=end_date)

    with st.spinner("Running Apify actor & fetching dataset items..."):
        run, items = run_actor_and_get_items(
            queries=queries,
            max_pages_per_query=max_pages,
            country_code=country.upper(),
            language_code=lang,
            safe_search=safe,
            limit_items=limit_items,
            tbs=tbs,
        )

    st.subheader("Run metadata")
    st.json(
        {
            "id": run.get("id"),
            "status": run.get("status"),
            "defaultDatasetId": run.get("defaultDatasetId"),
            "tbs_used": tbs,
        }
    )

    st.subheader("Raw dataset items (first 2)")
    st.json(items[:2] if isinstance(items, list) else items)

    st.subheader("Flattened organic results (best-effort)")
    df = flatten_organic(items if isinstance(items, list) else [])
    if df.empty:
        st.warning("No flattened results. Use the raw JSON above to adjust key mapping.")
    else:
        st.dataframe(df, use_container_width=True)
