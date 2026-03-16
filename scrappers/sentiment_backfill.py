"""
Historical Sentiment Backfill
=============================
Builds historical sentiment data from 2008 to today using PSX Announcements.

PSX provides official corporate events (dividends, earnings, rights, board meetings)
scored using rule-based sentiment weights.

Outputs sentiment_history.csv with PSX announcement-based sentiment.

Usage:
    python scrappers/sentiment_backfill.py
    python scrappers/sentiment_backfill.py --ticker OGDC
    python scrappers/sentiment_backfill.py --from 2022-01-01 --to 2024-12-31
"""

import sys
import io
import pandas as pd
from datetime import datetime

# Fix Unicode output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(__file__).replace("/scrappers/sentiment_backfill.py", "").replace("\\scrappers\\sentiment_backfill.py", ""))
from config import KSE30_STOCKS
from scrappers.psx_official import get_announcements_from_company_page


def backfill_historical_sentiment(from_date: str = "2008-01-01", to_date: str = None, tickers: list = None):
    """
    Backfill historical sentiment for all tickers from 2008 to today.
    Uses PSX announcements only (official corporate events).

    Args:
        from_date: start date (YYYY-MM-DD)
        to_date: end date (YYYY-MM-DD), defaults to today
        tickers: list of tickers, defaults to KSE30

    Outputs:
        data/processed/sentiment_history.csv
    """
    if to_date is None:
        to_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    if tickers is None:
        tickers = KSE30_STOCKS

    all_records = []

    print(f"\n=== Historical Sentiment Backfill: {from_date} to {to_date} (PSX Announcements Only) ===")
    print(f"Tickers: {len(tickers)}\n")

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {ticker}: fetching PSX announcements...")

        try:
            # Fetch all historical announcements for this ticker
            announcements = get_announcements_from_company_page(ticker, max_records=500)

            if not announcements:
                print(f"  → No announcements found")
                continue

            # Filter to date range
            filtered = [
                ann for ann in announcements
                if from_date <= ann["date"] <= to_date
            ]

            if not filtered:
                print(f"  → Found {len(announcements)} total, {len(filtered)} in date range")
                continue

            # Convert to sentiment records
            for ann in filtered:
                all_records.append({
                    "Date": ann["date"],
                    "Ticker": ticker,
                    "sentiment_score": float(ann["base_score"]),
                    "sentiment_count": 1,
                    "announcement_flag": 1,
                    "announcement_type": ann["ann_type"],
                    "key_headlines": f"['{ann['headline'][:150]}']\n",
                    "reasoning": f"PSX {ann['ann_type']} announcement",
                    "source": "psx_announcement"
                })

            print(f"  → {len(filtered)} announcements in range [{from_date}:{to_date}]")

        except Exception as e:
            print(f"  → Error: {str(e)[:100]}")
            continue

    # Save to CSV
    if all_records:
        df = pd.DataFrame(all_records)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values(["Date", "Ticker"]).reset_index(drop=True)

        output_path = "data/processed/sentiment_history.csv"
        df.to_csv(output_path, index=False)

        print(f"\n✅ Success!")
        print(f"   Saved {len(df)} records to {output_path}")
        print(f"   Date range: {df['Date'].min().date()} to {df['Date'].max().date()}")
        print(f"   Tickers with announcements: {df['Ticker'].nunique()}")
        print(f"   Announcement types: {df['announcement_type'].value_counts().to_dict()}")
        print(f"   Sentiment distribution: Mean={df['sentiment_score'].mean():.3f}, Std={df['sentiment_score'].std():.3f}")

        return df
    else:
        print("\n❌ No records collected!")
        return pd.DataFrame()


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Historical Sentiment Backfill (PSX Announcements Only)")
    parser.add_argument("--from", dest="from_date", default="2008-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--ticker", help="Single ticker (default: all KSE30)")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else None

    backfill_historical_sentiment(args.from_date, args.to_date, tickers)
