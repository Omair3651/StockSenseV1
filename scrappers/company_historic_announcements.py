"""
Company Historic Announcements Scraper (Selenium-based)
========================================================
Pulls ALL historical announcements for each KSE-30 company from PSX portal.
Uses Selenium to handle dynamic page loading and pagination.

Flow:
1. Load https://dps.psx.com.pk/announcements/companies (wait 20s for JS to load)
2. For each ticker: Enter symbol in form → view table → click Next until end
3. Extract all announcements: Date, Time, Symbol, CompanyName, Title
4. Save to CSV

Output: data/processed/company_historic_announcements.csv
Columns: Symbol, Date, Time, CompanyName, Title

Requirements:
    - selenium
    - webdriver-manager (for auto driver download)

Usage:
    python scrappers/company_historic_announcements.py
    python scrappers/company_historic_announcements.py --ticker OGDC
    python scrappers/company_historic_announcements.py --limit 5  # test on 5 tickers
    python scrappers/company_historic_announcements.py --headless  # no browser window
"""

import sys
import io
import pandas as pd
from datetime import datetime, date
import time
from pathlib import Path

# Fix Unicode output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(__file__).replace("/scrappers/company_historic_announcements.py", "").replace("\\scrappers\\company_historic_announcements.py", ""))
from config import KSE30_STOCKS

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"\n❌ Missing required package: {e}")
    print("\nInstall with:")
    print("  pip install selenium webdriver-manager beautifulsoup4 lxml")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────

BASE_URL = "https://dps.psx.com.pk/announcements/companies"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "company_historic_announcements.csv"

# Wait timeouts (seconds)
PAGE_LOAD_TIMEOUT = 20      # Initial page load
TABLE_LOAD_TIMEOUT = 10     # Wait for table after search
NEXT_BUTTON_TIMEOUT = 8     # Wait for next button click results

# Selectors for the page
SEARCH_INPUT_SELECTOR = "input#announcementsSearch"
SEARCH_BUTTON_SELECTOR = "button#annSearchBtn"
CLEAR_BUTTON_SELECTOR = "button#annClearBtn"
NEXT_BUTTON_SELECTOR = "button.form__button.next"
TABLE_SELECTOR = "table#announcementsTable"
TABLE_ROWS_SELECTOR = "table#announcementsTable tbody tr"
RESULTS_HEADER_SELECTOR = "div.announcementsResults__header"


# ── Core Scraper ───────────────────────────────────────────────────────────

def _setup_driver(headless: bool = False):
    """
    Initialize Chrome WebDriver.
    
    Args:
        headless: If True, run browser in headless mode (no window)
    
    Returns:
        Selenium WebDriver instance
    """
    options = webdriver.ChromeOptions()
    
    if headless:
        options.add_argument("--headless")
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    return driver


def _parse_date(date_str: str) -> str:
    """
    Parse date string from PSX page (e.g., "Mar 18, 2026") to YYYY-MM-DD.
    """
    date_str = date_str.strip()
    
    for fmt in ("%b %d, %Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return date.today().strftime("%Y-%m-%d")


def _extract_table_data(driver, ticker: str = None, page_num: int = 1):
    """
    Extract all visible announcement rows from the current table.
    
    Args:
        driver: Selenium WebDriver instance
        ticker: Stock symbol (for logging)
        page_num: Current page number (for logging)
    
    Returns:
        Tuple: (list of dicts, log_text)
    """
    records = []
    log_lines = []
    
    try:
        # Wait for table to be present
        WebDriverWait(driver, TABLE_LOAD_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, TABLE_ROWS_SELECTOR))
        )
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "lxml")
        table = soup.find("table", {"id": "announcementsTable"})
        
        if not table:
            return records, log_lines
        
        rows = table.select("tbody tr")
        
        for idx, row in enumerate(rows, 1):
            cols = row.select("td")
            if len(cols) < 5:
                continue
            
            date_str = cols[0].get_text(strip=True)
            time_str = cols[1].get_text(strip=True)
            symbol = cols[2].get_text(strip=True)
            company_name = cols[3].get_text(strip=True)
            title = cols[4].get_text(" ", strip=True)
            
            # Normalize
            title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            title = " ".join(title.split())
            
            raw_date = _parse_date(date_str)
            
            record = {
                "Symbol": symbol,
                "Date": raw_date,
                "Time": time_str,
                "CompanyName": company_name,
                "Title": title[:500],
            }
            records.append(record)
            
            # Log entry
            if ticker:
                log_lines.append(f"      [{page_num}-{idx:2d}] {symbol:6} | {raw_date} {time_str:7} | {company_name:20} | {title[:50]}")
    
    except Exception as e:
        log_lines.append(f"    ⚠ Table extraction error: {str(e)[:60]}")
    
    return records, log_lines


def scrape_ticker_announcements(driver, ticker: str) -> list[dict]:
    """
    Scrape ALL historical announcements for a single ticker.
    
    Args:
        driver: Selenium WebDriver instance
        ticker: Stock symbol (e.g., 'OGDC')
    
    Returns:
        List of dicts with announcement data
    """
    records = []
    
    print(f"\n  🔍 Searching: {ticker}")
    
    try:
        # CLEAR the form completely to reset pagination state from previous ticker
        try:
            clear_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, CLEAR_BUTTON_SELECTOR))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", clear_button)
            time.sleep(0.3)
            
            try:
                clear_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", clear_button)
            
            time.sleep(1)  # Wait for form to reset
            print(f"     ✓ Form cleared (pagination reset)")
        except Exception as e:
            print(f"     ⚠ Could not click CLEAR button: {str(e)[:50]}")
        
        # Now enter the new ticker
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR))
        )
        search_input.clear()
        time.sleep(0.5)
        
        # Enter ticker symbol
        search_input.send_keys(ticker)
        time.sleep(1)
        
        print(f"     ✓ Entered symbol: {ticker}")
        
        # Try to select from autocomplete dropdown if it appears
        try:
            # Wait for dropdown items to appear
            dropdown_items = WebDriverWait(driver, 2).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.autocomplete-item, li.autocomplete__item, button[role='option']"))
            )
            if dropdown_items:
                # Click the first matching option
                dropdown_items[0].click()
                time.sleep(0.5)
                print(f"     ✓ Selected from dropdown")
        except:
            # No dropdown or timeout - just continue with the text that was typed
            print(f"     ✓ No dropdown (proceeding with typed text)")
        
        # Find the Search button and click it
        search_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_BUTTON_SELECTOR))
        )
        
        # Scroll to button to ensure it's not covered
        driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
        time.sleep(0.3)
        
        # Wait for button to be clickable
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SEARCH_BUTTON_SELECTOR))
        )
        time.sleep(0.3)
        
        # Try to click the button
        try:
            search_button.click()
        except Exception:
            # If regular click fails, use JavaScript click
            driver.execute_script("arguments[0].click();", search_button)
        
        print(f"     ✓ Clicked SEARCH button")
        
        # Wait for results header to update with new data
        time.sleep(2)
        WebDriverWait(driver, TABLE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, RESULTS_HEADER_SELECTOR))
        )
        
        # Extract first page
        page_data, logs = _extract_table_data(driver, ticker=ticker, page_num=1)
        
        if not page_data:
            print(f"     ✗ No results found for {ticker}")
            return records
        
        records.extend(page_data)
        print(f"     📄 PAGE 1: {len(page_data)} entries")
        for log in logs[:5]:  # Show first 5 entries
            print(log)
        if len(logs) > 5:
            print(f"      ... ({len(logs) - 5} more entries)")
        
        # Paginate through results
        page_num = 2
        consecutive_empty = 0
        
        while True:
            try:
                # Find all next buttons (refetch to avoid stale references)
                next_buttons = driver.find_elements(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
                
                clicked = False
                for btn in next_buttons:
                    try:
                        # Check if button is disabled
                        if "disabled" not in btn.get_attribute("class"):
                            # Store current rows for staleness check
                            try:
                                old_rows = driver.find_elements(By.CSS_SELECTOR, TABLE_ROWS_SELECTOR)
                                if old_rows:
                                    old_row_ref = old_rows[0]
                                else:
                                    old_row_ref = None
                            except:
                                old_row_ref = None
                            
                            # Scroll to button and click
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            time.sleep(0.3)
                            
                            try:
                                btn.click()
                            except Exception:
                                # Fallback to JavaScript click
                                driver.execute_script("arguments[0].click();", btn)
                            
                            # Wait for old rows to disappear (DOM refresh)
                            if old_row_ref:
                                try:
                                    WebDriverWait(driver, NEXT_BUTTON_TIMEOUT).until(
                                        EC.staleness_of(old_row_ref)
                                    )
                                except:
                                    pass  # Continue anyway
                            
                            # Wait a bit for new data to render
                            time.sleep(1.5)
                            
                            clicked = True
                            break
                    except Exception as btn_err:
                        # Skip this button and try next one
                        continue
                
                if not clicked:
                    # No more enabled next buttons
                    break
                
                # Extract data from new page
                page_data, logs = _extract_table_data(driver, ticker=ticker, page_num=page_num)
                
                if not page_data:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        # Two consecutive empty pages means we've hit pagination end
                        break
                else:
                    consecutive_empty = 0
                    records.extend(page_data)
                    print(f"     📄 PAGE {page_num}: {len(page_data)} entries")
                    for log in logs[:5]:  # Show first 5 entries
                        print(log)
                    if len(logs) > 5:
                        print(f"      ... ({len(logs) - 5} more entries)")
                    page_num += 1
                
            except Exception as e:
                # Error during pagination, stop gracefully
                break
        
        print(f"     ✅ Total for {ticker}: {len(records)} records\n")
        
    except Exception as e:
        print(f"     ✗ Error: {str(e)[:100]}\n")
    
    return records


# ── Main ───────────────────────────────────────────────────────────────────

def main(tickers: list[str] = None, headless: bool = False):
    """
    Main orchestrator: Scrape announcements for all tickers.
    
    Args:
        tickers: List of tickers to scrape. If None, uses all KSE30_STOCKS
        headless: Run browser in headless mode
    """
    if tickers is None:
        tickers = KSE30_STOCKS
    
    all_records = []
    driver = None
    ticker_results = {}
    
    try:
        # Initialize WebDriver
        print("\n" + "=" * 80)
        print("📊 STOCK ANNOUNCEMENTS SCRAPER (PSX Portal)")
        print("=" * 80)
        print(f"\n📊 Initializing Chrome WebDriver...")
        driver = _setup_driver(headless=headless)
        
        print(f"⏳ Loading base page: {BASE_URL}")
        driver.get(BASE_URL)
        
        # Wait for initial page render
        print(f"⏳ Waiting {PAGE_LOAD_TIMEOUT}s for JavaScript to load...")
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR))
        )
        print("✓ Page loaded successfully\n")
        
        # Scrape each ticker
        print(f"📝 Starting scrape for {len(tickers)} tickers...")
        print("=" * 80)
        
        for idx, ticker in enumerate(tickers, 1):
            print(f"\n[{idx:2d}/{len(tickers)}] {ticker}")
            ticker_records = scrape_ticker_announcements(driver, ticker)
            all_records.extend(ticker_records)
            ticker_results[ticker] = len(ticker_records)
            time.sleep(1)  # Brief pause between tickers
        
        print("=" * 80)
        print(f"\n✅ SCRAPING COMPLETE\n")
        
        # Summary
        print("📊 SUMMARY BY TICKER:")
        print("-" * 80)
        total_by_sector = {}
        for ticker, count in sorted(ticker_results.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ticker:8} → {count:6,d} announcements")
            total_by_sector[ticker] = count
        
        print("-" * 80)
        print(f"  {'TOTAL':8} → {len(all_records):6,d} announcements")
        print(f"  {'UNIQUE':8} → (will be calculated after dedup)")
        print("=" * 80)
        
        # Save to CSV
        if all_records:
            df = pd.DataFrame(all_records)
            
            # Sort by Date desc, then by Symbol
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.sort_values(["Date", "Symbol"], ascending=[False, True])
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
            
            # Remove duplicates (Symbol + Date + Title)
            df_dedup = df.drop_duplicates(subset=["Symbol", "Date", "Title"], keep="first")
            
            # Save
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            df_dedup.to_csv(OUTPUT_PATH, index=False)
            
            print(f"\n✅ SAVED TO CSV")
            print(f"   Path: {OUTPUT_PATH}")
            print(f"   Total records collected: {len(all_records):,d}")
            print(f"   After deduplication: {len(df_dedup):,d} unique records")
            print(f"   Date range: {df['Date'].min()} to {df['Date'].max()}")
            print(f"   Columns: {', '.join(df_dedup.columns.tolist())}")
            print("=" * 80)
        else:
            print("\n⚠ No announcements collected")
    
    except Exception as e:
        print(f"\n✗ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            print("\n🔌 Closing browser...")
            driver.quit()
            print("✓ Browser closed")
            print("=" * 80)


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Scrape historical PSX announcements for KSE-30 stocks using Selenium."
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Scrape single ticker (e.g., OGDC). If not provided, scrapes all KSE-30.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no window).",
    )
    
    args = parser.parse_args()
    
    if args.ticker:
        main(tickers=[args.ticker.upper()], headless=args.headless)
    else:
        main(headless=args.headless)
