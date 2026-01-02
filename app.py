import urllib.parse
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Apify Google Scraper Test", layout="wide")

# Secrets must be set in Streamlit Cloud:
# APIFY_TOKEN="..."
# APIFY_ACTOR_ID="apify/google-search-scraper"
APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
ACTOR_ID = st.secrets.get("APIFY_ACTOR_ID", "apify/google-search-scraper")


def run_actor_and_get_items(
    queries,
    max_pages_per_query=1,
    country_code="US",
    language_code="en",
    safe_search="active",
    wait_for_finish=120,
    limit_items=200,
):
    """
    Runs apify/google-search-scraper and returns:
      - run metadata
      - dataset items (JSON)

    NOTE: Actor input/output fields can vary slightly. This script shows raw JSON too,
    so you can map keys precisely if needed.
    """
    run_url = f"https://api.apify.com/v2/acts/{urllib.parse.quote(ACTOR_ID)}/runs"
    params = {"token": APIFY_TOKEN, "waitForFinish": wait_for_finish}

    payload = {
        "queries": [{"query": q} for q in queries],
        "maxPagesPerQuery": max_pages_per_query,
        "countryCode": country_code,
        "languageCode": language_code,
        "safeSearch": safe_search,
    }

    r = requests.post(run_url, params=params, json=payload, timeout=wait_for_finish + 30)
    r.raise_for_status()
    run = r.json()["data"]

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(
            "No defaultDatasetId returned. "
            f"Run keys: {list(run.keys())}"
        )

    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    items_params = {
        "token": APIFY_TOKEN,
        "clean": "true",
        "limit": limit_items,
    }
    items_resp = requests.get(items_url, params=items_params, timeout=60)
    items_resp.raise_for_status()
    items = items_resp.json()

    return run, items


def flatten_organic(items):
    """
    Best-effort flattener for common Apify output shapes:
      - items[i].organicResults[] OR items[i].organic_results[]
      - OR items[] already represent result rows

    If your dataset schema differs, you'll still see raw JSON preview above.
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
            # fallback if item itself looks like a row
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

    # remove google redirect links if they appear
    df = df[~df["link"].str.contains("google.com/url", na=False)]

    # dedupe by link
    df = df.drop_duplicates(subset=["link"])

    # optional: quick tag for PR-ish pages
    kw = ["new study", "survey", "report", "findings", "new research", "announced", "press release"]
    df["likely_pr"] = df["snippet"].fillna("").str.lower().apply(lambda s: any(k in s for k in kw))

    # nice ordering
    cols = ["likely_pr", "query", "title", "source", "date", "link", "snippet"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


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

    run_btn = st.button("Run test")


if run_btn:
    queries = [q.strip() for q in raw_queries.splitlines() if q.strip()]
    if not queries:
        st.error("Please enter at least one query.")
        st.stop()

    try:
        with st.spinner("Running Apify actor & fetching dataset items..."):
            run, items = run_actor_and_get_items(
                queries=queries,
                max_pages_per_query=max_pages,
                country_code=country.upper(),
                language_code=lang,
                safe_search=safe,
                limit_items=limit_items,
            )
    except requests.HTTPError as e:
        st.error("Apify request failed.")
        st.code(getattr(e.response, "text", str(e)))
        st.stop()
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    st.success("Done.")

    st.subheader("Run metadata")
    st.json(
        {
            "id": run.get("id"),
            "status": run.get("status"),
            "defaultDatasetId": run.get("defaultDatasetId"),
            "startedAt": run.get("startedAt"),
            "finishedAt": run.get("finishedAt"),
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
            "No flattened results yet. This usually means the actor output schema is different.\n\n"
            "Use the raw JSON preview above to identify the correct field names, then update flatten_organic()."
        )
    else:
        st.dataframe(df, use_container_width=True)
