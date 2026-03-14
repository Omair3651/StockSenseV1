"""
PSX Official Scraper
====================
Scrapes two sources from the PSX DPS portal:
  1. Announcements — dps.psx.com.pk/announcements
     Corporate events per ticker: dividends, earnings, rights issues, board notices.
  2. Company page — dps.psx.com.pk/company/<TICKER>
     Financial highlights, key ratios, sector info.

Run directly to test a single ticker:
    python scrappers/psx_official.py --ticker OGDC
    python scrappers/psx_official.py --ticker OGDC --from 2023-01-01 --to 2023-12-31
"""

import sys
import argparse
import requests
import time
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__).replace("/scrappers/psx_official.py", "").replace("\\scrappers\\psx_official.py", ""))
from config import REQUEST_HEADERS, REQUEST_TIMEOUT, ANNOUNCEMENT_SCORES

# ── Announcement keyword classifier ────────────────────────────────────────

def _classify_announcement(text: str) -> str:
    """Return announcement type based on keywords in the text."""
    t = text.lower()
    if any(k in t for k in ['dividend', 'div ', 'cash dividend', 'final dividend', 'interim dividend']):
        return 'dividend'
    if any(k in t for k in ['earnings', 'financial results', 'profit', 'loss', 'eps', 'revenue', 'quarterly results', 'annual results']):
        return 'earnings'
    if any(k in t for k in ['rights issue', 'right shares', 'rights share']):
        return 'rights'
    if any(k in t for k in ['board of directors', 'board meeting', 'board of director']):
        return 'board'
    return 'other'


def _base_score(ann_type: str, text: str) -> float:
    """
    Rule-based base score for an announcement.
    For earnings, tries to detect beat/miss from text.
    """
    if ann_type == 'earnings':
        t = text.lower()
        if any(k in t for k in ['increased', 'rose', 'up by', 'growth', 'record profit', 'surged']):
            return 0.50
        if any(k in t for k in ['declined', 'fell', 'down by', 'loss', 'deficit', 'decreased']):
            return -0.50
        return 0.0
    return ANNOUNCEMENT_SCORES.get(ann_type, 0.0)


# ── Announcements scraper ──────────────────────────────────────────────────

def get_announcements(ticker: str,
                      from_date: str = None,
                      to_date: str = None,
                      max_pages: int = 5) -> list[dict]:
    """
    Scrape PSX announcements for a ticker.

    Args:
        ticker:    e.g. 'OGDC'
        from_date: 'YYYY-MM-DD', defaults to 30 days ago
        to_date:   'YYYY-MM-DD', defaults to today
        max_pages: safety cap on pagination

    Returns:
        List of dicts:
            ticker, date, headline, ann_type, base_score, source, weight
    """
    if from_date is None:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if to_date is None:
        to_date = date.today().strftime('%Y-%m-%d')

    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    records = []
    url = "https://dps.psx.com.pk/announcements"

    for page in range(1, max_pages + 1):
        payload = {
            "symbol": ticker,
            "from":   from_date,
            "to":     to_date,
            "page":   page,
        }
        try:
            resp = session.post(url, data=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [psx_official] {ticker} page {page} request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Try to find the announcements table (inspect HTML structure)
        table = soup.find("table")
        if not table:
            # No table found — print a snippet so we can debug the actual structure
            print(f"  [psx_official] {ticker}: no <table> found on page {page}. "
                  f"Response snippet: {resp.text[:400]!r}")
            break

        rows = table.select("tbody tr")
        if not rows:
            break  # No more data

        page_count = 0
        for row in rows:
            cols = [td.get_text(" ", strip=True) for td in row.select("td")]
            if len(cols) < 2:
                continue

            # Typical PSX announcement table: Date | Company | Headline | ...
            # Column positions can vary — we search for the date in the first few cols
            raw_date = None
            headline = ""
            for i, col in enumerate(cols):
                # Try to parse as date
                for fmt in ("%b %d, %Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        raw_date = datetime.strptime(col.strip(), fmt).strftime("%Y-%m-%d")
                        headline = " ".join(cols[i+1:]).strip() if i + 1 < len(cols) else cols[-1]
                        break
                    except ValueError:
                        continue
                if raw_date:
                    break

            if not raw_date:
                # Fallback: use today's date, treat entire row as headline
                raw_date = date.today().strftime("%Y-%m-%d")
                headline = " | ".join(cols)

            ann_type = _classify_announcement(headline)
            score    = _base_score(ann_type, headline)

            records.append({
                "ticker":     ticker,
                "date":       raw_date,
                "headline":   headline[:300],
                "ann_type":   ann_type,
                "base_score": score,
                "source":     "psx_announcement",
                "weight":     2.0,
            })
            page_count += 1

        print(f"  [psx_official] {ticker} page {page}: {page_count} announcements")

        # Check for a "next page" link; stop if none
        next_link = soup.find("a", string=lambda s: s and ("next" in s.lower() or "›" in s))
        if not next_link:
            break

        time.sleep(0.5)  # be polite

    return records


# ── Company page scraper ───────────────────────────────────────────────────

def get_company_info(ticker: str) -> dict:
    """
    Scrape the PSX company detail page for a ticker.
    Returns a dict with whatever financial highlights are available.
    """
    url = f"https://dps.psx.com.pk/company/{ticker}"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [psx_official] Company page {ticker} failed: {e}")
        return {"ticker": ticker, "error": str(e)}

    soup = BeautifulSoup(resp.text, "lxml")
    info = {"ticker": ticker, "url": url}

    # Extract all key-value pairs from definition lists and table cells
    # The page uses various layouts — we grab everything visible
    for dl in soup.find_all("dl"):
        terms = dl.find_all("dt")
        values = dl.find_all("dd")
        for dt, dd in zip(terms, values):
            key = dt.get_text(strip=True).lower().replace(" ", "_")
            val = dd.get_text(" ", strip=True)
            info[key] = val

    for table in soup.find_all("table"):
        for row in table.select("tr"):
            cells = row.select("td, th")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).lower().replace(" ", "_")
                val = cells[1].get_text(" ", strip=True)
                info[key] = val

    # Also grab the page title / company name
    title_tag = soup.find("h1") or soup.find("h2")
    if title_tag:
        info["company_name"] = title_tag.get_text(strip=True)

    # Summarise all text for Gemini context (first 800 chars of visible text)
    page_text = soup.get_text(" ", strip=True)
    info["page_summary"] = page_text[:800]

    print(f"  [psx_official] {ticker} company page: {len(info)} fields scraped")
    return info


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSX Official Scraper")
    parser.add_argument("--ticker", default="OGDC", help="Ticker symbol")
    parser.add_argument("--from",   dest="from_date", default=None, help="From date YYYY-MM-DD")
    parser.add_argument("--to",     dest="to_date",   default=None, help="To date YYYY-MM-DD")
    parser.add_argument("--pages",  type=int, default=3, help="Max announcement pages")
    args = parser.parse_args()

    print(f"\n=== PSX Announcements: {args.ticker} ===")
    anns = get_announcements(args.ticker, args.from_date, args.to_date, args.pages)
    if anns:
        for a in anns:
            print(f"  {a['date']} | {a['ann_type']:10s} | score={a['base_score']:+.2f} | {a['headline'][:80]}")
    else:
        print("  No announcements found.")

    print(f"\n=== PSX Company Page: {args.ticker} ===")
    info = get_company_info(args.ticker)
    for k, v in info.items():
        if k != "page_summary":
            print(f"  {k}: {v}")
    if "page_summary" in info:
        print(f"  page_summary (first 200 chars): {info['page_summary'][:200]}")
