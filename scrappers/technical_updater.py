import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import yfinance as yf
import os
import sys
import io
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix Unicode output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==========================================
# 1. CONFIGURATION
# ==========================================
MASTER_CSV_PATH = 'data/processed/stocksense_tft_final.csv'

KSE30_STOCKS = [
    'OGDC', 'PPL', 'POL', 'HUBC', 'ENGRO', 'FFC', 'EFERT', 'LUCK', 'MCB', 'UBL',
    'HBL', 'BAHL', 'MEBL', 'NBP', 'FABL', 'BAFL', 'DGKC', 'MLCF', 'FCCL', 'CHCC',
    'PSO', 'SHEL', 'ATRL', 'PRL', 'SYS', 'SEARL', 'ILP', 'TGL', 'INIL', 'PAEL'
]

SECTOR_MAP = {
    'OGDC': 'Energy', 'PPL': 'Energy', 'POL': 'Energy', 'HUBC': 'Power',
    'ENGRO': 'Fertilizer', 'FFC': 'Fertilizer', 'EFERT': 'Fertilizer',
    'LUCK': 'Cement', 'DGKC': 'Cement', 'MLCF': 'Cement', 'FCCL': 'Cement', 'CHCC': 'Cement',
    'MCB': 'Banking', 'UBL': 'Banking', 'HBL': 'Banking', 'BAHL': 'Banking', 
    'MEBL': 'Banking', 'NBP': 'Banking', 'FABL': 'Banking', 'BAFL': 'Banking',
    'PSO': 'OMC', 'SHEL': 'OMC', 'ATRL': 'Refinery', 'PRL': 'Refinery',
    'SYS': 'Tech', 'SEARL': 'Pharma', 'ILP': 'Textile', 'TGL': 'Glass',
    'INIL': 'Engineering', 'PAEL': 'Engineering'
}

class PSXIncrementalScraper:
    def __init__(self):
        self.url = "https://dps.psx.com.pk/historical"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120'}
        self.session = requests.Session()

    def fetch_month(self, symbol, year, month):
        payload = {"symbol": symbol, "month": month, "year": year}
        data = []
        try:
            r = self.session.post(self.url, data=payload, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="historicalTable")
            if table:
                for row in table.select("tbody tr"):
                    cols = [td.get_text(strip=True) for td in row.select("td")]
                    if len(cols) == 6:
                        data.append({
                            "Date": datetime.strptime(cols[0], "%b %d, %Y").date(),
                            "Open": float(cols[1].replace(",","")),
                            "High": float(cols[2].replace(",","")),
                            "Low": float(cols[3].replace(",","")),
                            "Close": float(cols[4].replace(",","")),
                            "Volume": int(cols[5].replace(",","")),
                            "Ticker": symbol
                        })
        except: pass
        return data

def get_required_months(start_date, end_date):
    months = []
    curr = start_date.replace(day=1)
    while curr <= end_date:
        months.append((curr.year, curr.month))
        curr = (curr + timedelta(days=32)).replace(day=1)
    return months

def calculate_new_indicators(df, master_max_idx_map):
    df = df.sort_values(['Ticker', 'Date'])
    
    def get_rsi(series, window=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
        return 100 - (100 / (1 + (gain / (loss + 1e-9))))

    results = []
    for ticker, group in df.groupby('Ticker'):
        g = group.copy()
        g['sma_20'] = g['Close'].rolling(20).mean()
        g['sma_50'] = g['Close'].rolling(50).mean()
        g['rsi_14'] = get_rsi(g['Close'])
        g['vol_20'] = g['Close'].pct_change().rolling(20).std()
        
        # Safely continue time_idx
        start_idx = master_max_idx_map.get(ticker, -1) + 1
        mask_new = g['time_idx'].isna()
        if mask_new.any():
            new_count = mask_new.sum()
            g.loc[mask_new, 'time_idx'] = np.arange(start_idx, start_idx + new_count)
            
        results.append(g)
    
    return pd.concat(results)

def main():
    if not os.path.exists(MASTER_CSV_PATH):
        print(f"Error: Could not find {MASTER_CSV_PATH}. Please run the full scraper first.")
        return

    print("--- Reading Master Data ---")
    master_df = pd.read_csv(MASTER_CSV_PATH)
    master_df['Date'] = pd.to_datetime(master_df['Date']).dt.date
    
    last_date = master_df['Date'].max()
    today = date.today()
    
    if last_date >= today:
        print("✅ Data is already up to date. No new records to fetch.")
        return
        
    print(f"--- Fetching Missing Data: {last_date + timedelta(days=1)} to {today} ---")
    
    scraper = PSXIncrementalScraper()
    months_to_fetch = get_required_months(last_date, today)
    all_tickers = KSE30_STOCKS + ['KSE100']
    
    tasks = []
    for ticker in all_tickers:
        for year, month in months_to_fetch:
            tasks.append((ticker, year, month))
            
    new_data = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {executor.submit(scraper.fetch_month, *t): t for t in tasks}
        for future in tqdm(as_completed(future_to_task), total=len(tasks), desc="Scraping Months"):
            new_data.extend(future.result())
            
    if not new_data:
        print("⚠️ No new data points returned from PSX (Market may be closed).")
        return
        
    new_df = pd.DataFrame(new_data)
    # Strictly filter to dates after the master file's last date
    new_df = new_df[new_df['Date'] > last_date]
    
    if new_df.empty:
        print("⚠️ No new data points after filtering.")
        return

    print("--- Processing New KSE100 & Macro ---")
    kse100 = new_df[new_df['Ticker'] == 'KSE100'][['Date', 'Close']].rename(columns={'Close': 'market_index'})
    stocks = new_df[new_df['Ticker'] != 'KSE100'].copy()
    stocks = pd.merge(stocks, kse100, on='Date', how='left')
    
    print("Fetching new USD/PKR rates...")
    usd = yf.download("PKR=X", start=last_date, end=today + timedelta(days=1), progress=False)['Close'].reset_index()
    usd.columns = ['Date', 'USD_PKR']
    usd['Date'] = pd.to_datetime(usd['Date']).dt.date
    stocks = pd.merge(stocks, usd, on='Date', how='left')
    
    stocks['Sector'] = stocks['Ticker'].map(SECTOR_MAP)
    stocks['day_of_week'] = pd.to_datetime(stocks['Date']).dt.dayofweek
    stocks['month'] = pd.to_datetime(stocks['Date']).dt.month
    
    # Forward fill missing macro variables
    stocks = stocks.sort_values(['Ticker', 'Date'])
    stocks[['market_index', 'USD_PKR']] = stocks.groupby('Ticker')[['market_index', 'USD_PKR']].ffill()

    print("--- Calculating Indicators with Historical Buffer ---")
    # Grab the last 70 days from the master file to act as a lookback buffer
    buffer_date = last_date - timedelta(days=70)
    history_buffer = master_df[master_df['Date'] >= buffer_date].copy()
    
    # Map the max time_idx per ticker to continue the TFT sequence correctly
    max_idx_map = master_df.groupby('Ticker')['time_idx'].max().to_dict()
    
    # Combine buffer and new data for calculation
    combined = pd.concat([history_buffer, stocks], ignore_index=True).drop_duplicates(subset=['Date', 'Ticker'])
    calculated = calculate_new_indicators(combined, max_idx_map)
    
    # Isolate ONLY the new rows after calculation
    final_new_rows = calculated[calculated['Date'] > last_date].copy()
    
    # Merge back into master and save
    print("--- Saving Updated Master File ---")
    final_master = pd.concat([master_df, final_new_rows], ignore_index=True)
    final_master = final_master.sort_values(['Ticker', 'Date'])
    final_master.to_csv(MASTER_CSV_PATH, index=False)
    
    print(f"✅ Success! Appended {len(final_new_rows)} new records. Master dataset is now up to date.")

if __name__ == "__main__":
    main()