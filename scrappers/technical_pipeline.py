import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import yfinance as yf
import os
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. CONFIGURATION
# ==========================================
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

class PSXFullScraper:
    def __init__(self):
        self.url = "https://dps.psx.com.pk/historical"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120'}
        self.session = requests.Session()

    def fetch_month(self, symbol, year, month):
        """Scrapes a single month for a symbol"""
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
                            "Date": datetime.strptime(cols[0], "%b %d, %Y"),
                            "Open": float(cols[1].replace(",","")),
                            "High": float(cols[2].replace(",","")),
                            "Low": float(cols[3].replace(",","")),
                            "Close": float(cols[4].replace(",","")),
                            "Volume": int(cols[5].replace(",","")),
                            "Ticker": symbol
                        })
        except:
            pass
        return data

    def scrape_all_history(self, symbol, start_year=2000):
        """Scrapes all months from start_year to today using threading"""
        today = datetime.now()
        tasks = []
        for year in range(start_year, today.year + 1):
            end_month = today.month if year == today.year else 12
            for month in range(1, end_month + 1):
                tasks.append((symbol, year, month))

        all_results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_task = {executor.submit(self.fetch_month, *t): t for t in tasks}
            for future in as_completed(future_to_task):
                all_results.extend(future.result())
        
        return pd.DataFrame(all_results)

# ==========================================
# 2. FEATURE ENGINEERING
# ==========================================
def add_tft_features(df):
    df = df.sort_values(['Ticker', 'Date'])
    
    # Technical Indicators
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
        g['time_idx'] = np.arange(len(g))
        results.append(g)
    
    return pd.concat(results)

# ==========================================
# 3. RUN PIPELINE
# ==========================================
if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs('data/raw', exist_ok=True)
    os.makedirs('data/processed', exist_ok=True)

    scraper = PSXFullScraper()
    all_tickers = KSE30_STOCKS + ['KSE100']
    full_data_list = []

    print(f"--- Starting COMPLETE scrape (2000 to {date.today()}) ---")
    for ticker in tqdm(all_tickers, desc="Scraping Tickers"):
        df_ticker = scraper.scrape_all_history(ticker)
        if not df_ticker.empty:
            full_data_list.append(df_ticker)

    # Combine
    master_df = pd.concat(full_data_list).drop_duplicates()
    master_df.to_csv('data/raw/full_scrape_backup.csv', index=False)

    print("--- Processing Market Index (KSE100) & Macro ---")
    # Pivot KSE100
    kse100 = master_df[master_df['Ticker'] == 'KSE100'][['Date', 'Close']].rename(columns={'Close': 'market_index'})
    stocks = master_df[master_df['Ticker'] != 'KSE100'].copy()
    
    # Merge Index
    stocks = pd.merge(stocks, kse100, on='Date', how='left')
    
    # Fetch Currency (USD/PKR)
    print("Fetching Currency Data...")
    usd = yf.download("PKR=X", start="2000-01-01")['Close'].reset_index()
    usd.columns = ['Date', 'USD_PKR']
    stocks = pd.merge(stocks, usd, on='Date', how='left')

    # Forward fill gaps
    stocks = stocks.sort_values(['Ticker', 'Date'])
    stocks[['market_index', 'USD_PKR']] = stocks.groupby('Ticker')[['market_index', 'USD_PKR']].ffill()

    print("--- Engineering TFT Ready Features ---")
    stocks['Sector'] = stocks['Ticker'].map(SECTOR_MAP)
    stocks['day_of_week'] = stocks['Date'].dt.dayofweek
    stocks['month'] = stocks['Date'].dt.month
    
    final_df = add_tft_features(stocks)
    final_df = final_df.dropna() # Remove initial NaN windows

    final_df.to_csv('data/processed/stocksense_tft_final.csv', index=False)
    print(f"--- SUCCESS! Final dataset: {len(final_df)} rows. Saved to data/processed/stocksense_tft_final.csv ---")