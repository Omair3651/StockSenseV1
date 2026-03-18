import pandas as pd
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from pygooglenews import GoogleNews
    HAS_GOOGLENEWS = True
except:
    HAS_GOOGLENEWS = False

# ---------------------- CONFIG ----------------------

KSE30 = [
    "LUCK", "ENGRO", "HBL", "UBL", "MCB", "OGDC",
    "PPL", "PSO", "HUBC", "FFC", "TRG", "SYS",
    "EFERT", "BAHL", "DAWH", "COLG", "SEARL",
    "MARI", "PIOC", "POL", "INIL", "GHGL",
    "UNITY", "AIRLINK", "AVN", "DGKC", "FCCL",
    "NESTLE", "INDU"
]

SITES = [
    "dawn.com",
    "brecorder.com",
    "thenews.com.pk",
    "profit.pakistantoday.com.pk",
    "tribune.com.pk",
    "arynews.tv",
    "geo.tv",
    "samaa.tv"
]

DATE_RANGES = ["1d", "7d", "1m", "3m", "6m", "1y"]

MAX_WORKERS = 10
OUTPUT_FILE = f"kse30_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ---------------------- LOGGING ----------------------

logging.basicConfig(
    filename="rss_news.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

# ---------------------- QUERY BUILDER ----------------------

def build_queries(ticker):
    queries = [
        f"{ticker} stock Pakistan",
        f"{ticker} KSE",
        f"{ticker} earnings",
        f"{ticker} financial results",
        f"{ticker} Pakistan company",
        f"{ticker} share price"
    ]

    # Add site-specific queries
    for site in SITES:
        queries.append(f"site:{site} {ticker}")

    return queries

# ---------------------- PYGOOGLENEWS FETCH ----------------------

def fetch_pygooglenews(ticker, query, date_range):
    results = []
    try:
        gn = GoogleNews(lang='en', country='PK')
        news = gn.search(query, when=date_range)

        for entry in news.get('entries', []):
            results.append({
                "ticker": ticker,
                "source": "pygooglenews",
                "query": query,
                "title": entry.get('title', ''),
                "link": entry.get('link', ''),
                "published": entry.get('published', ''),
                "summary": entry.get('summary', '')
            })

    except Exception as e:
        logging.warning(f"pygooglenews failed: {query} | {e}")

    return results

# ---------------------- GOOGLE RSS FETCH ----------------------

def fetch_rss(ticker, query):
    results = []

    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-PK&gl=PK&ceid=PK:en"

        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0"
        }, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "xml")
            items = soup.find_all("item")

            for item in items:
                results.append({
                    "ticker": ticker,
                    "source": "rss",
                    "query": query,
                    "title": item.title.text if item.title else "",
                    "link": item.link.text if item.link else "",
                    "published": item.pubDate.text if item.pubDate else "",
                    "summary": item.description.text if item.description else ""
                })

    except Exception as e:
        logging.warning(f"RSS failed: {query} | {e}")

    return results

# ---------------------- COMBINED FETCH ----------------------

def fetch_all_sources(ticker, query, date_range):
    results = []

    if HAS_GOOGLENEWS:
        results.extend(fetch_pygooglenews(ticker, query, date_range))

    results.extend(fetch_rss(ticker, query))

    return results

# ---------------------- MAIN ----------------------

def main():
    logging.info("=" * 60)
    logging.info("KSE-30 NEWS (RSS + PYGOOGLENEWS)")
    logging.info("=" * 60)

    all_news = []

    for ticker in KSE30:
        logging.info(f"\nProcessing: {ticker}")
        queries = build_queries(ticker)

        for query in queries:
            for dr in DATE_RANGES:
                logging.info(f"Query: {query} | {dr}")

                results = fetch_all_sources(ticker, query, dr)
                all_news.extend(results)

                logging.info(f"→ {len(results)} articles")

                time.sleep(0.5)

    logging.info(f"\nTotal collected: {len(all_news)}")

    if not all_news:
        logging.warning("No data collected")
        return

    df = pd.DataFrame(all_news)

    # ---------------------- CLEAN ----------------------

    df.drop_duplicates(subset=["link"], inplace=True)

    df["published"] = pd.to_datetime(df["published"], errors="coerce")

    df = df[df["title"].str.len() > 5]

    logging.info(f"After cleaning: {len(df)}")

    # ---------------------- SAVE ----------------------

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    logging.info(f"\nSaved to: {OUTPUT_FILE}")
    logging.info(f"Rows: {len(df)}")

# ---------------------- RUN ----------------------

if __name__ == "__main__":
    main()