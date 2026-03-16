"""
Phase 2: Merge + Validate TFT Dataset
=====================================
Combines technical data + sentiment history + daily sentiment into a unified,
production-ready dataset for Temporal Fusion Transformer (TFT) training.

Pipeline:
  1. Load and fix sentiment data (re-score PSX announcements)
  2. Unify sentiment_history + sentiment_daily → sentiment_all.csv
  3. Left-join with technical data
  4. Fill sentiment gaps (forward-fill + zero-fill)
  5. Add derived features (sentiment_ma_5, days_since_announcement)
  6. Validate integrity
  7. Save → tft_ready.csv (123k rows × 23 columns)

Usage:
    python merge_datasets.py
"""

import sys
import io
import pandas as pd
import numpy as np
from pathlib import Path

# Fix Unicode output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Configuration ────────────────────────────────────────────────────────────

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "processed"

TFT_CSV        = DATA_DIR / "stocksense_tft_final.csv"
HIST_CSV       = DATA_DIR / "sentiment_history.csv"
DAILY_CSV      = DATA_DIR / "sentiment_daily.csv"
SENTIMENT_ALL  = DATA_DIR / "sentiment_all.csv"
OUTPUT_CSV     = DATA_DIR / "tft_ready.csv"

# Rule-based scoring for PSX announcements (re-applied because sentiment_history.csv has all 0.0)
ANNOUNCEMENT_SCORES = {
    "dividend": 0.60,
    "rights":   0.30,
    "earnings": 0.0,   # ambiguous without financial data
    "board":    0.0,   # procedural, no sentiment
    "other":    0.0,
}

# Feature engineering parameters
FFILL_LIMIT  = 5    # max consecutive days to forward-fill sentiment
DSA_CAP      = 30   # cap for days_since_announcement feature
ROLLING_WIN  = 5    # window for sentiment_ma_5

# Final output columns (23 total)
FINAL_COLS = [
    "Date", "Ticker", "Sector", "Open", "High", "Low", "Close", "Volume",
    "market_index", "USD_PKR", "day_of_week", "month", "sma_20", "sma_50",
    "rsi_14", "vol_20", "time_idx",
    "sentiment_score", "sentiment_count", "announcement_flag",
    "announcement_type", "sentiment_ma_5", "days_since_announcement",
]


# ── Step 1: Load + Fix Sentiment ─────────────────────────────────────────────

def load_sentiment_history(path: Path) -> pd.DataFrame:
    """
    Load sentiment_history.csv and re-score from announcement_type.

    CRITICAL: sentiment_history.csv has all sentiment_score=0.0 because
    get_announcements_from_company_page() doesn't apply rule-based scoring.
    This function fixes that.
    """
    df = pd.read_csv(path, parse_dates=["Date"])

    # Re-score based on announcement_type (overwrite all 0.0 values)
    df["sentiment_score"] = (
        df["announcement_type"].str.strip().str.lower().map(ANNOUNCEMENT_SCORES).fillna(0.0)
    )

    # Keep only the 9 columns we need
    cols = ["Date", "Ticker", "sentiment_score", "sentiment_count",
            "announcement_flag", "announcement_type", "key_headlines", "reasoning", "source"]
    return df[cols].copy()


def load_sentiment_daily(path: Path) -> pd.DataFrame:
    """
    Load sentiment_daily.csv and inject missing source column.
    """
    df = pd.read_csv(path, parse_dates=["Date"])

    # sentiment_daily.csv is missing the source column — inject it
    df["source"] = "groq_tavily"

    # Match column order to history
    cols = ["Date", "Ticker", "sentiment_score", "sentiment_count",
            "announcement_flag", "announcement_type", "key_headlines", "reasoning", "source"]
    return df[cols].copy()


def unify_sentiment(hist: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """
    Combine sentiment_history + sentiment_daily.
    On conflict (same Date, Ticker), keep daily (Tavily+Groq > rule-based).
    """
    # Concat with history first, daily second → keep="last" favors daily
    combined = pd.concat([hist, daily], ignore_index=True)

    # Dedup: keep the latest row for each (Date, Ticker) pair
    combined = combined.sort_values(["Date", "Ticker"]).drop_duplicates(
        subset=["Date", "Ticker"], keep="last"
    )

    return combined.reset_index(drop=True)


# ── Step 2: Merge with Technical Data ────────────────────────────────────────

def merge_with_technical(tft: pd.DataFrame, sentiment: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join TFT base with sentiment data on [Date, Ticker].
    """
    # Ensure both have same data types for merge
    tft["Date"] = pd.to_datetime(tft["Date"])
    sentiment["Date"] = pd.to_datetime(sentiment["Date"])

    # Keep only columns we need from sentiment
    sentiment_cols = ["Date", "Ticker", "sentiment_score", "sentiment_count",
                      "announcement_flag", "announcement_type"]

    # Left-join: keep all TFT rows, match sentiment where available
    merged = tft.merge(
        sentiment[sentiment_cols],
        on=["Date", "Ticker"],
        how="left"
    )

    return merged


# ── Step 3: Fill Sentiment Gaps ──────────────────────────────────────────────

def fill_sentiment_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill sentiment_score (up to FFILL_LIMIT days) then zero-fill.
    Do NOT forward-fill announcement_flag — only set on actual announcement days.
    """
    # Sort by ticker and date (mandatory before groupby operations)
    df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    # Forward-fill sentiment_score per ticker (up to 5 consecutive NaN days)
    df["sentiment_score"] = (
        df.groupby("Ticker")["sentiment_score"]
          .transform(lambda s: s.ffill(limit=FFILL_LIMIT))
    )

    # Zero-fill remaining NaNs
    df["sentiment_score"]    = df["sentiment_score"].fillna(0.0)
    df["sentiment_count"]    = df["sentiment_count"].fillna(0).astype(int)
    df["announcement_flag"]  = df["announcement_flag"].fillna(0).astype(int)
    df["announcement_type"]  = df["announcement_type"].fillna("")

    return df


# ── Step 4: Derived Features ─────────────────────────────────────────────────

def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute sentiment_ma_5 and days_since_announcement.
    """

    # Feature 1: sentiment_ma_5 — 5-day rolling mean per ticker
    df["sentiment_ma_5"] = (
        df.groupby("Ticker")["sentiment_score"]
          .transform(lambda s: s.rolling(window=ROLLING_WIN, min_periods=1).mean())
    )

    # Feature 2: days_since_announcement — days since last announcement_flag=1
    def compute_days_since_announcement(group):
        """Compute days since last announcement for a single ticker group."""
        flags = group["announcement_flag"].values
        dates = pd.to_datetime(group["Date"]).values
        result = np.full(len(group), DSA_CAP, dtype=int)

        last_ann_date = None
        for i, (flag, date) in enumerate(zip(flags, dates)):
            if flag == 1:
                last_ann_date = date
                result[i] = 0  # day of announcement
            elif last_ann_date is not None:
                # Days since last announcement (capped at DSA_CAP)
                delta = (date - last_ann_date) / np.timedelta64(1, 'D')
                result[i] = min(int(delta), DSA_CAP)
            # else: no prior announcement → stays at DSA_CAP

        return pd.Series(result, index=group.index)

    df["days_since_announcement"] = (
        df.groupby("Ticker", group_keys=False).apply(compute_days_since_announcement)
    )

    return df


# ── Step 7: Validation ───────────────────────────────────────────────────────

def validate(df: pd.DataFrame) -> bool:
    """
    Run comprehensive validation checks. Return True if all critical checks pass.
    """
    all_pass = True

    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)

    # Check 1: Shape
    rows, cols = df.shape
    shape_pass = (cols == len(FINAL_COLS))
    status = "[PASS]" if shape_pass else "[FAIL]"
    print(f"{status} Shape: ({rows:,} rows, {cols} columns)")
    if not shape_pass:
        print(f"       Expected {len(FINAL_COLS)} columns, got {cols}")
        all_pass = False

    # Check 2: Date range (informational)
    min_date = df["Date"].min().date()
    max_date = df["Date"].max().date()
    print(f"[INFO] Date range: {min_date} to {max_date}")

    # Check 3: Ticker coverage
    n_tickers = df["Ticker"].nunique()
    ticker_pass = (n_tickers == 30)
    status = "[PASS]" if ticker_pass else "[FAIL]"
    print(f"{status} Ticker coverage: {n_tickers} unique tickers")
    if not ticker_pass:
        all_pass = False

    # Check 4: Sentiment coverage (informational)
    nonzero_pct = (df["sentiment_score"] != 0.0).sum() / len(df) * 100
    ann_pct = (df["announcement_flag"] == 1).sum() / len(df) * 100
    print(f"[INFO] Sentiment coverage: {nonzero_pct:.2f}% non-zero | {ann_pct:.2f}% with flag=1")

    # Check 5: Null check
    null_counts = df[FINAL_COLS].isnull().sum()
    total_nulls = null_counts.sum()
    null_pass = (total_nulls == 0)
    status = "[PASS]" if null_pass else "[FAIL]"
    print(f"{status} Null check: {total_nulls} nulls across all columns")
    if not null_pass:
        print("       Columns with nulls:")
        for col, count in null_counts[null_counts > 0].items():
            print(f"         {col}: {count}")
        all_pass = False

    # Check 6: time_idx continuity per ticker
    def check_time_idx_continuity(group):
        diffs = group["time_idx"].diff().dropna()
        return (diffs == 1.0).all() if len(diffs) > 0 else True

    continuity = df.groupby("Ticker").apply(check_time_idx_continuity)
    continuity_pass = continuity.all()
    status = "[PASS]" if continuity_pass else "[FAIL]"
    print(f"{status} time_idx continuity: all tickers gap-free")
    if not continuity_pass:
        broken = continuity[~continuity].index.tolist()
        print(f"       Broken tickers: {broken}")
        all_pass = False

    # Check 7: Duplicate (Date, Ticker) pairs
    dupes = df.duplicated(subset=["Date", "Ticker"]).sum()
    dupe_pass = (dupes == 0)
    status = "[PASS]" if dupe_pass else "[FAIL]"
    print(f"{status} Duplicate (Date,Ticker): {dupes} duplicates")
    if not dupe_pass:
        all_pass = False

    # Check 8: Sanity check — announcement rows have non-null sentiment
    ann_rows = df[df["announcement_flag"] == 1]
    has_nan_on_ann = ann_rows["sentiment_score"].isnull().any()
    sanity_pass = not has_nan_on_ann
    status = "[PASS]" if sanity_pass else "[FAIL]"
    print(f"{status} Sanity: no NaN sentiment on announcement rows")
    if not sanity_pass:
        all_pass = False

    print("=" * 60)

    return all_pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("PHASE 2: MERGE + VALIDATE TFT DATASET")
    print("=" * 70)

    print("\n=== STEP 0: Load Inputs ===")
    print(f"  Loading TFT base: {TFT_CSV.name}")
    tft = pd.read_csv(TFT_CSV, parse_dates=["Date"])
    tft["time_idx"] = tft["time_idx"].astype(int)
    print(f"    ✓ {tft.shape[0]:,} rows × {tft.shape[1]} columns")

    print("\n=== STEP 1: Fix + Unify Sentiment ===")
    print(f"  Loading sentiment_history.csv (and re-scoring)...")
    hist = load_sentiment_history(HIST_CSV)
    print(f"    ✓ {hist.shape[0]} rows (re-scored from announcement_type)")

    print(f"  Loading sentiment_daily.csv (and adding source column)...")
    daily = load_sentiment_daily(DAILY_CSV)
    print(f"    ✓ {daily.shape[0]} rows")

    print(f"  Unifying both sources (dedup on (Date,Ticker), keep daily)...")
    sentiment = unify_sentiment(hist, daily)
    print(f"    ✓ {sentiment.shape[0]} unified rows")

    sentiment.to_csv(SENTIMENT_ALL, index=False)
    print(f"    ✓ Saved {SENTIMENT_ALL.name}")

    print("\n=== STEP 2: Merge with Technical Data ===")
    print(f"  Left-joining TFT + sentiment on [Date, Ticker]...")
    merged = merge_with_technical(tft, sentiment)
    print(f"    ✓ {merged.shape[0]:,} rows × {merged.shape[1]} columns")

    print("\n=== STEP 3: Fill Sentiment Gaps ===")
    print(f"  Forward-filling sentiment_score (up to {FFILL_LIMIT} days per ticker)...")
    filled = fill_sentiment_gaps(merged)
    ffill_count = (merged["sentiment_score"].isnull().sum() -
                   filled["sentiment_score"].isnull().sum())
    print(f"    ✓ Forward-filled {ffill_count} values")
    print(f"  Zero-filling remaining gaps...")
    zero_count = filled["sentiment_score"].isnull().sum()
    print(f"    ✓ {zero_count} nulls remaining (all will be zero-filled)")

    print("\n=== STEP 4: Derived Sentiment Features ===")
    print(f"  Computing sentiment_ma_5...")
    featured = add_derived_features(filled)
    print(f"    ✓ Added sentiment_ma_5 (5-day rolling mean per ticker)")
    print(f"  Computing days_since_announcement...")
    print(f"    ✓ Added days_since_announcement (days since last flag=1, capped at {DSA_CAP})")

    print("\n=== STEP 5: Finalize Column Order ===")
    print(f"  Reordering to {len(FINAL_COLS)} final columns...")
    featured = featured[FINAL_COLS].copy()

    # Handle any remaining nulls in technical indicator columns (e.g., sma_50 on latest date)
    tech_cols = ["Open", "High", "Low", "Close", "Volume", "market_index", "USD_PKR",
                 "sma_20", "sma_50", "rsi_14", "vol_20"]
    for col in tech_cols:
        if featured[col].isnull().any():
            featured[col] = featured.groupby("Ticker")[col].transform(
                lambda x: x.ffill()  # forward-fill nulls within each ticker
            )

    print(f"    ✓ {featured.shape[0]:,} rows × {featured.shape[1]} columns")

    print("\n=== STEP 6: Save Output ===")
    featured.to_csv(OUTPUT_CSV, index=False)
    print(f"  ✓ Saved {OUTPUT_CSV.name} ({featured.shape[0]:,} rows)")

    print("\n=== STEP 7: Validate ===")
    passed = validate(featured)

    if passed:
        print("\n✅ SUCCESS! Dataset is ready for TFT training.")
        print(f"   Output: {OUTPUT_CSV}")
        print(f"   Shape: {featured.shape[0]:,} rows × {featured.shape[1]} columns")
    else:
        print("\n❌ VALIDATION FAILED! Review errors above.")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
