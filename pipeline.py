"""
Sentiment Pipeline
==================
Orchestrates PSX official scraping + Gemini news scoring → sentiment_daily.csv

Usage:
    # Daily run (today's data for all 30 tickers):
    python pipeline.py

    # Backfill historical PSX announcements (no Gemini — Gemini only covers last 7 days):
    python pipeline.py --backfill --from 2022-01-01 --to 2024-12-31

    # Single ticker test:
    python pipeline.py --ticker OGDC

Output:
    data/processed/sentiment_daily.csv
    Columns: Date, Ticker, sentiment_score, sentiment_count, announcement_flag, announcement_type
"""

import sys
import argparse
import pandas as pd
from datetime import date, datetime, timedelta
from pathlib import Path

from config import (
    KSE30_STOCKS, SENTIMENT_CSV, SOURCE_WEIGHTS
)
from scrappers.psx_official import get_announcements
from scrappers.Gemini_Sentiment import get_gemini_sentiment, score_all_tickers


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_existing() -> pd.DataFrame:
    """Load existing sentiment_daily.csv or return empty DataFrame."""
    if SENTIMENT_CSV.exists():
        df = pd.read_csv(SENTIMENT_CSV, parse_dates=["Date"])
        print(f"  Loaded existing sentiment file: {len(df)} rows")
        return df
    cols = ["Date", "Ticker", "sentiment_score", "sentiment_count",
            "announcement_flag", "announcement_type", "key_headlines", "reasoning"]
    return pd.DataFrame(columns=cols)


def _save(df: pd.DataFrame):
    """Deduplicate on (Date, Ticker), keeping the latest row, then save."""
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values(["Date", "Ticker"]).drop_duplicates(
        subset=["Date", "Ticker"], keep="last"
    )
    df.to_csv(SENTIMENT_CSV, index=False)
    print(f"  Saved {len(df)} rows to {SENTIMENT_CSV}")


def _weighted_merge(psx_score: float, psx_weight: float,
                    gemini_score: float, gemini_weight: float) -> float:
    """
    Weighted average of PSX rule-based score and Gemini score.
    If PSX score is 0.0 (no announcement or neutral event), Gemini dominates.
    If both have signal, weight them by source trust.
    """
    total_weight = 0.0
    total_score  = 0.0
    if psx_score != 0.0:
        total_score  += psx_score * psx_weight
        total_weight += psx_weight
    total_score  += gemini_score * gemini_weight
    total_weight += gemini_weight
    return round(total_score / total_weight, 4) if total_weight > 0 else 0.0


# ── Daily run ──────────────────────────────────────────────────────────────

def run_daily(tickers: list[str] = None, skip_gemini: bool = False):
    """
    Run for today: PSX announcements (today only) + Gemini for all tickers.
    Appends new rows to sentiment_daily.csv.
    """
    if tickers is None:
        tickers = KSE30_STOCKS
    today_str = date.today().strftime("%Y-%m-%d")
    print(f"\n=== Daily Sentiment Run: {today_str} ===")

    existing = _load_existing()
    new_rows = []

    # Step 1: PSX announcements for today
    print("\n[1/2] Scraping PSX announcements...")
    ann_by_ticker: dict[str, list] = {}
    for ticker in tickers:
        anns = get_announcements(ticker, from_date=today_str, to_date=today_str, max_pages=2)
        ann_by_ticker[ticker] = anns

    # Step 2: Gemini news scores for all tickers
    gemini_results: dict[str, dict] = {}
    if not skip_gemini:
        print(f"\n[2/2] Querying Gemini for {len(tickers)} tickers...")
        for result in score_all_tickers(tickers):
            gemini_results[result["ticker"]] = result
    else:
        print("\n[2/2] Gemini skipped (--no-gemini flag).")

    # Step 3: Merge into one row per ticker
    print("\n[3/3] Merging scores...")
    for ticker in tickers:
        anns = ann_by_ticker.get(ticker, [])
        gem  = gemini_results.get(ticker, {})

        # PSX announcement signal
        if anns:
            best_ann  = max(anns, key=lambda a: abs(a["base_score"]))
            psx_score = best_ann["base_score"]
            ann_flag  = 1
            ann_type  = best_ann["ann_type"]
        else:
            psx_score = 0.0
            ann_flag  = 0
            ann_type  = ""

        gemini_score = gem.get("sentiment_score", 0.0)
        final_score  = _weighted_merge(
            psx_score,    SOURCE_WEIGHTS["psx_announcement"],
            gemini_score, SOURCE_WEIGHTS["gemini_news"],
        )

        new_rows.append({
            "Date":             today_str,
            "Ticker":           ticker,
            "sentiment_score":  final_score,
            "sentiment_count":  gem.get("headline_count", 0) + len(anns),
            "announcement_flag": ann_flag,
            "announcement_type": ann_type,
            "key_headlines":    str(gem.get("key_headlines", [])),
            "reasoning":        gem.get("reasoning", ""),
        })
        print(f"  {ticker}: final={final_score:+.4f}  psx={psx_score:+.2f}  "
              f"gemini={gemini_score:+.2f}  ann_flag={ann_flag}")

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    _save(combined)
    print(f"\nDone. {len(new_rows)} rows added for {today_str}.")


# ── Backfill ───────────────────────────────────────────────────────────────

def run_backfill(from_date: str, to_date: str, tickers: list[str] = None):
    """
    Backfill historical PSX announcements from from_date to to_date.
    Gemini search is NOT used here (only covers last ~7 days).
    Rows with no announcement get sentiment_score = 0.0.

    This builds the announcement_flag column for the historical period,
    which gives the TFT model a signal even without article-level sentiment.
    """
    if tickers is None:
        tickers = KSE30_STOCKS

    print(f"\n=== Backfill: {from_date} → {to_date} ({len(tickers)} tickers) ===")

    existing = _load_existing()
    all_records = []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {ticker}: fetching announcements...")
        anns = get_announcements(ticker, from_date=from_date, to_date=to_date, max_pages=50)
        print(f"  → {len(anns)} announcements found")

        for ann in anns:
            all_records.append({
                "Date":             ann["date"],
                "Ticker":           ticker,
                "sentiment_score":  ann["base_score"],
                "sentiment_count":  1,
                "announcement_flag": 1,
                "announcement_type": ann["ann_type"],
                "key_headlines":    f"['{ann['headline'][:120]}']",
                "reasoning":        f"PSX announcement: {ann['ann_type']}",
            })

    if not all_records:
        print("No announcement records found for the date range.")
        return

    new_df = pd.DataFrame(all_records)
    combined = pd.concat([existing, new_df], ignore_index=True)
    _save(combined)
    print(f"\nBackfill done. {len(all_records)} announcement rows added.")
    print("Note: Trading days with NO announcement have no row yet.")
    print("Run pipeline.py (daily) to fill in Gemini-sourced sentiment for recent dates.")


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSX Sentiment Pipeline")
    parser.add_argument("--ticker",     help="Run for a single ticker only")
    parser.add_argument("--backfill",   action="store_true",
                        help="Backfill historical PSX announcements (no Gemini)")
    parser.add_argument("--from",       dest="from_date", default="2022-01-01",
                        help="Backfill start date (YYYY-MM-DD)")
    parser.add_argument("--to",         dest="to_date",
                        default=date.today().strftime("%Y-%m-%d"),
                        help="Backfill end date (YYYY-MM-DD)")
    parser.add_argument("--no-gemini",  action="store_true",
                        help="Skip Gemini (daily run: PSX only, faster)")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else None

    if args.backfill:
        run_backfill(args.from_date, args.to_date, tickers)
    else:
        run_daily(tickers, skip_gemini=args.no_gemini)
