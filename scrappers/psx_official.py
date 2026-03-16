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


def _extract_csrf(html: str) -> str:
    """
    Extract CSRF token from PSX page HTML.
    Looks for: <meta name="csrf-token" content="..."> or <input name="_token" value="...">
    """
    soup = BeautifulSoup(html, "lxml")

    # Try meta tag first (common in Laravel)
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta.get("content")

    # Try input field as fallback
    token_input = soup.find("input", {"name": "_token"})
    if token_input and token_input.get("value"):
        return token_input.get("value")

    return ""


# ── Announcements scraper ──────────────────────────────────────────────────

def get_announcements_from_company_page(ticker: str, max_records: int = 20) -> list[dict]:
    """
    Fallback scraper: Extract announcements directly from company page.
    Used when the main announcements endpoint fails.
    
    Args:
        ticker: e.g. 'OGDC'
        max_records: max announcements to return
    
    Returns:
        List of dicts with announcement data
    """
    url = f"https://dps.psx.com.pk/company/{ticker}"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [psx_official] Fallback announcements from company page {ticker} failed: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, "lxml")
    records = []
    
    # Extract from announcements section (Financial Results, Board Meetings, Others)
    announcements_section = soup.find("div", {"id": "announcementsTab"})
    if announcements_section:
        ann_tables = announcements_section.find_all("table")
        for ann_table in ann_tables:
            tbody = ann_table.find("tbody")
            if tbody:
                rows = tbody.find_all("tr")
                for row in rows[:max_records]:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        date_str = cells[0].get_text(strip=True)
                        headline = cells[1].get_text(strip=True)
                        
                        # Parse date
                        raw_date = None
                        for fmt in ("%b %d, %Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                            try:
                                raw_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                                break
                            except ValueError:
                                continue
                        
                        if not raw_date:
                            raw_date = date.today().strftime("%Y-%m-%d")
                        
                        headline = " ".join(headline.split())  # Normalize whitespace
                        ann_type = _classify_announcement(headline)
                        score = _base_score(ann_type, headline)
                        
                        records.append({
                            "ticker":     ticker,
                            "date":       raw_date,
                            "headline":   headline[:300],
                            "ann_type":   ann_type,
                            "base_score": score,
                            "source":     "psx_company_page",
                            "weight":     1.5,
                        })
    
    print(f"  [psx_official] {ticker} announcements from company page: {len(records)} records")
    return records


def get_announcements(ticker: str,
                      from_date: str = None,
                      to_date: str = None,
                      max_pages: int = 5,
                      use_fallback: bool = True) -> list[dict]:
    """
    Scrape PSX announcements for a ticker.
    Falls back to company page if announcements endpoint fails.

    Args:
        ticker:    e.g. 'OGDC'
        from_date: 'YYYY-MM-DD', defaults to 30 days ago
        to_date:   'YYYY-MM-DD', defaults to today
        max_pages: safety cap on pagination
        use_fallback: try company page if endpoint fails

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
    base_url = "https://dps.psx.com.pk/announcements"
    endpoint_failed = False
    csrf_token = ""

    # Step 1: GET the announcements page once to establish session + extract CSRF token
    try:
        init_resp = session.get(base_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        if init_resp.status_code == 200:
            csrf_token = _extract_csrf(init_resp.text)
            if csrf_token:
                print(f"  [psx_official] {ticker}: CSRF token extracted, starting pagination...")
        else:
            print(f"  [psx_official] {ticker}: initial GET failed (HTTP {init_resp.status_code}), attempting POST without token")
    except requests.RequestException as e:
        print(f"  [psx_official] {ticker}: initial GET failed ({e}), attempting POST without token")

    for page in range(1, max_pages + 1):
        # Prepare payload with CSRF token if available
        payload = {
            "symbol": ticker,
            "from":   from_date,
            "to":     to_date,
            "page":   page,
        }
        if csrf_token:
            payload["_token"] = csrf_token

        try:
            # Prepare headers with AJAX indicators
            headers = REQUEST_HEADERS.copy()
            headers['Referer'] = 'https://dps.psx.com.pk/announcements'
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers['X-Requested-With'] = 'XMLHttpRequest'

            # POST with CSRF token + AJAX header
            resp = session.post(base_url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)

            # If 500 error, try GET as fallback
            if resp.status_code == 500:
                resp = session.get(base_url, params=payload, headers=headers, timeout=REQUEST_TIMEOUT)

            # Both failed, mark as failed
            if resp.status_code >= 400:
                print(f"  [psx_official] {ticker} page {page}: HTTP {resp.status_code}")
                endpoint_failed = True
                break

            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [psx_official] {ticker} page {page} request failed: {e}")
            endpoint_failed = True
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Find the announcements table by id
        table = soup.find("table", {"id": "announcementsTable"})
        if not table:
            table = soup.find("table")
        
        if not table:
            print(f"  [psx_official] {ticker}: no <table> found on page {page}")
            endpoint_failed = True
            break

        rows = table.select("tbody tr")
        if not rows:
            print(f"  [psx_official] {ticker}: no rows in table on page {page}")
            break  # No more data

        page_count = 0
        for row in rows:
            cols = [td.get_text(" ", strip=True) for td in row.select("td")]
            if len(cols) < 3:
                continue

            # PSX announcement table structure: DATE | TIME | TITLE | (PDF LINK)
            # Column 0: Date (e.g., "Mar 13, 2026")
            # Column 1: Time (e.g., "7:14 PM")
            # Column 2: Title/Headline
            # Column 3+: Links/PDFs
            
            date_str = cols[0].strip()
            headline = cols[2].strip() if len(cols) > 2 else ""
            
            # Parse the date
            raw_date = None
            for fmt in ("%b %d, %Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    raw_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            
            if not raw_date:
                # Fallback to today if parsing fails
                raw_date = date.today().strftime("%Y-%m-%d")

            # Remove any HTML entities and normalize whitespace
            headline = headline.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            headline = " ".join(headline.split())  # Normalize whitespace

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

        # Check for a "next page" button that is not disabled
        next_buttons = soup.find_all("button", {"class": "form__button next"})
        has_next = False
        for btn in next_buttons:
            if "disabled" not in btn.get("class", []):
                has_next = True
                break
        
        if not has_next:
            break

        time.sleep(0.5)  # be polite

    # If endpoint failed and fallback is enabled, try company page
    if endpoint_failed and use_fallback:
        if not records:
            print(f"  [psx_official] {ticker}: announcements endpoint failed, using company page fallback...")
            records = get_announcements_from_company_page(ticker)
        else:
            print(f"  [psx_official] {ticker}: endpoint fallback complete, {len(records)} records from company page")

    return records


# ── Company page scraper ───────────────────────────────────────────────────

def get_company_info(ticker: str) -> dict:
    """
    Scrape the PSX company detail page for a ticker.
    Returns a dict with financial highlights, ratios, payouts, and other company data.
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

    # ── Extract Company Name ──────────────────────────────────────────────
    quote_section = soup.find("div", {"class": "quote__details"})
    if quote_section:
        name_tag = quote_section.find("div", {"class": "quote__name"})
        if name_tag:
            info["company_name"] = name_tag.get_text(strip=True).split('\n')[0]
        
        sector_tag = quote_section.find("div", {"class": "quote__sector"})
        if sector_tag:
            info["sector"] = sector_tag.get_text(strip=True)
        
        # Current price info
        price_tag = quote_section.find("div", {"class": "quote__close"})
        if price_tag:
            info["current_price"] = price_tag.get_text(strip=True)

    # ── Extract Profile Information ────────────────────────────────────────
    profile_section = soup.find("div", {"class": "company__profile"})
    if profile_section:
        # Business Description
        desc_item = profile_section.find("div", {"class": "profile__item--decription"})
        if desc_item:
            desc_tag = desc_item.find("p")
            if desc_tag:
                info["business_description"] = desc_tag.get_text(strip=True)
        
        # Key People
        people_table = profile_section.find("table")
        if people_table:
            rows = people_table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) == 2:
                    name = cells[0].get_text(strip=True)
                    role = cells[1].get_text(strip=True)
                    info[f"person_{role.lower()}"] = name
        
        # Address, Website, Registrar, Auditor
        profile_items = profile_section.find_all("div", {"class": "profile__item"})
        for item in profile_items:
            heading = item.find("div", {"class": "item__head"})
            if heading:
                key = heading.get_text(strip=True).lower().replace(" ", "_")
                content = item.get_text(" ", strip=True)
                # Remove the heading from content
                content = content.replace(heading.get_text(strip=True), "", 1).strip()
                if content:
                    info[key] = content[:500]  # Limit length

    # ── Extract Financials ────────────────────────────────────────────────
    # Look for tables with financial data
    all_tables = soup.find_all("table", {"class": "tbl"})
    
    for table in all_tables:
        thead = table.find("thead")
        tbody = table.find("tbody")
        
        if not thead or not tbody:
            continue
        
        rows = tbody.find_all("tr")
        if not rows:
            continue
        
        # Determine table type by checking first row label
        first_row_label = rows[0].find("td")
        if not first_row_label:
            continue
        
        first_label = first_row_label.get_text(strip=True).lower()
        is_financial_table = "sales" in first_label or "revenue" in first_label
        is_ratios_table = "gross profit" in first_label or "net profit" in first_label
        
        # Process rows based on table type
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            
            label = cells[0].get_text(strip=True).lower()
            values = [c.get_text(strip=True) for c in cells[1:]]
            
            # Financial table rows
            if is_financial_table:
                if "sales" in label:
                    info["financial_sales"] = values
                elif "profit after" in label:
                    info["financial_profit_after_tax"] = values
                elif label == "eps":
                    info["financial_eps"] = values
            
            # Ratios table rows
            elif is_ratios_table:
                if "gross profit margin" in label:
                    info["ratio_gross_profit_margin"] = values
                elif "net profit margin" in label:
                    info["ratio_net_profit_margin"] = values
                elif "eps growth" in label:
                    info["ratio_eps_growth"] = values
                elif "peg" in label:
                    info["ratio_peg"] = values

    # ── Extract Payouts Information ────────────────────────────────────────
    payouts = []
    payouts_section = soup.find("div", {"class": "company__payouts"})
    if payouts_section:
        payouts_table = payouts_section.find("table")
        if payouts_table:
            tbody = payouts_table.find("tbody")
            if tbody:
                rows = tbody.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 4:
                        payout_record = {
                            "date": cells[0].get_text(strip=True),
                            "financial_results": cells[1].get_text(strip=True),
                            "details": cells[2].get_text(strip=True),
                            "book_closure": cells[3].get_text(strip=True),
                        }
                        payouts.append(payout_record)
    
    if payouts:
        info["payouts"] = payouts

    # ── Extract Announcements from Company Page ────────────────────────────
    announcements = []
    announcements_section = soup.find("div", {"id": "announcementsTab"})
    if announcements_section:
        # Financial Results tab is usually selected/first
        ann_tables = announcements_section.find_all("table")
        for ann_table in ann_tables:
            tbody = ann_table.find("tbody")
            if tbody:
                rows = tbody.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        ann_record = {
                            "date": cells[0].get_text(strip=True),
                            "title": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                            "document": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                        }
                        announcements.append(ann_record)
    
    if announcements:
        info["announcements"] = announcements

    # ── Summary ────────────────────────────────────────────────────────────
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
    
    # Display info excluding complex nested structures
    skip_keys = {"page_summary", "announcements", "payouts"}
    for k, v in info.items():
        if k not in skip_keys:
            print(f"  {k}: {v}")
    
    # Display payouts if available
    if "payouts" in info and info["payouts"]:
        print(f"\n  Payouts ({len(info['payouts'])} records):")
        for payout in info["payouts"]:
            print(f"    {payout['date']:20s} | {payout['financial_results']:15s} | {payout['details']}")
    
    # Display announcements if available
    if "announcements" in info and info["announcements"]:
        print(f"\n  Announcements ({len(info['announcements'])} records):")
        for ann in info["announcements"][:5]:  # Show first 5
            print(f"    {ann['date']:15s} | {ann['title'][:70]}")
        if len(info["announcements"]) > 5:
            print(f"    ... and {len(info['announcements']) - 5} more")
    
    if "page_summary" in info:
        print(f"\n  page_summary (first 200 chars): {info['page_summary'][:200]}")
