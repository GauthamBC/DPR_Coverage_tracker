import urllib.parse
import requests
import pandas as pd
import streamlit as st
from datetime import date, timedelta

st.set_page_config(page_title="Apify Google Search Scraper — Preview", layout="wide")

# --- Secrets (set in Streamlit Cloud)
APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
ACTOR_ID_RAW = st.secrets.get("APIFY_ACTOR_ID", "apify/google-search-scraper")


# --- Helpers
def normalize_actor_id(actor_id: str) -> str:
    """
    Apify API expects actors as 'user~actor' (tilde), not 'user/actor' (slash).
    This converts 'user/actor' -> 'user~actor' when needed.
    """
    actor_id = actor_id.strip()
    if "/" in actor_id and "~" not in actor_id:
        parts = actor_id.split("/")
        if len(parts) == 2:
            return f"{parts[0]}~{parts[1]}"
    return actor_id


ACTOR_ID = normalize_actor_id(ACTOR_ID_RAW)


def build_tbs(preset: str, start: date | None = None, end: date | None = None) -> str | None:
    """
    Google time filters (tbs):
      - Past day: qdr:d
      - Past week: qdr:w
      - Past month: qdr:m
      - Past year: qdr:y
      - Custom: cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY
    """
    preset = preset.strip().lower()
    today = date.today()

    if preset == "any time":
        return None
    if preset == "last 24 hours":
        return "qdr:d"
    if preset == "last 48 hours":
        # no native 48h shortcut; approximate using a 2-day custom window
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
    wait_for_finish=180,
    limit_items=200,
    tbs: str | None = None,
):
    """
    Runs Apify actor and returns (run_metadata, dataset_items).
    """
    actor_for_url = urllib.parse.quote(ACTOR_ID, safe="")
    run_url = f"https://api.apify.com/v2/acts/{actor_for_url}/runs"
    params = {"token": APIFY_TOKEN, "waitForFinish": wait_for_finish}

    # Actor input fields can vary slightly by version;
    # these are common for apify/google-search-scraper.
    payload = {
        "queries": [{"query": q} for q in queries],
        "maxPagesPerQuery": max_pages_per_query,
        "countryCode": country_code,
        "languageCode": language_code,
        "safeSearch": safe_search,
    }

    # If supported, this will apply the time filter.
    # If not supported, it will be ignored (but safe).
    if tbs:
        payload["tbs"] = tbs

    r = requests.post(run_url, params=params, json=payload, timeout=wait_for_finish + 30)
    r.raise_for_status()
    run = r.json()["data"]

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(f"No defaultDatasetId returned. Run keys: {list(run.keys())}")

    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    items_params = {"token": APIFY_TOKEN, "clean": "true", "limit": limit_items}
    items_resp = requests.get(items_url, params=items_params, timeout=90)
    items_resp.raise_for_status()

    return run, items_resp.json()


def flatten_organic(items):
    """
    Best-effort flattening for common output shapes.
    Adjust this after you inspect your dataset JSON once.
    """
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
            # fallback if items are already individual rows
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
    df = df[~df["link"].str.contains("google.com/url", na=False)]
    df = df.drop_duplicates(subset=["link"])

    kw = ["new study", "survey", "report", "findings", "new research", "announced", "press release"]
    df["likely_pr"] = df["snippet"].fillna("").str.lower().apply(lambda s: any(k in s for k in kw))

    cols = ["likely_pr", "query", "title", "source", "date", "link", "snippet"]
    for c in cols:
        if c not in df.columns:
            df[c] = None

    return df[cols]


# --- UI
st.title("Apify Google Search Scraper — Output Preview")

with st.sidebar:
    st.header("Apify")
    st.caption(f"Actor: {ACTOR_ID}")

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
        if start_date and end_date and start_date > end_date:
            st.warning("Start date must be on/before end date.")

    run_btn = st.button("Run test")


if run_btn:
    queries = [q.strip() for q in raw_queries.splitlines() if q.strip()]
    if not queries:
        st.error("Please enter at least one query.")
        st.stop()

    tbs = build_tbs(preset, start=start_date, end=end_date)

    try:
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
    except requests.HTTPError as e:
        st.error("Apify request failed (HTTP error).")
        st.code(getattr(e.response, "text", str(e)))
        st.stop()
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    st.success("Done.")

    st.subheader("Run metadata")
    st.json(
        {
            "actor_used": ACTOR_ID,
            "run_id": run.get("id"),
            "status": run.get("status"),
            "defaultDatasetId": run.get("defaultDatasetId"),
            "startedAt": run.get("startedAt"),
            "finishedAt": run.get("finishedAt"),
            "tbs_used": tbs,
        }
    )

    st.subheader("Raw dataset items (first 2)")
    if isinstance(items, list):
        st.json(items[:2])
        st.caption(f"Total items fetched: {len(items)}")
    else:
        st.json(items)

    st.subheader("Flattened organic results (best-effort)")
    df = flatten_organic(items if isinstance(items, list) else [])
    if df.empty:
        st.warning(
            "No flattened results. This means the actor output schema is different.\n\n"
            "Use the raw JSON above to identify the correct keys and update flatten_organic()."
        )
    else:
        st.dataframe(df, use_container_width=True)
