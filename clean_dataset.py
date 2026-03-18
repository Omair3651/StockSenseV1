"""
Dataset Cleaning Script - Fixes data quality issues before TFT training
"""

import pandas as pd
import numpy as np
import sys
import io

# Fix Unicode
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 90)
print("DATASET CLEANING - Fixing Data Quality Issues")
print("=" * 90)

# Load original dataset
df = pd.read_csv('data/processed/tft_ready.csv')
original_len = len(df)
df['Date'] = pd.to_datetime(df['Date'])

print(f"\nStarting with {len(df):,} rows")

# ====== ISSUE 1: Close Price Outside [Low, High] ======
print("\n[1] FIXING: Close price outside [Low, High] range")
print("-" * 90)

outside_range = ((df['Close'] < df['Low']) | (df['Close'] > df['High'])).sum()
print(f"Found {outside_range} problematic rows")

if outside_range > 0:
    # For these rows, use the midpoint of [Low, High] as Close
    mask = (df['Close'] < df['Low']) | (df['Close'] > df['High'])
    df.loc[mask, 'Close'] = (df.loc[mask, 'Low'] + df.loc[mask, 'High']) / 2
    print(f"✅ Fixed by using midpoint of [Low, High]")

    # Verify
    still_outside = ((df['Close'] < df['Low']) | (df['Close'] > df['High'])).sum()
    print(f"After fix: {still_outside} rows still problematic")

# ====== ISSUE 2: Zero Volume Records ======
print("\n[2] HANDLING: Zero volume records")
print("-" * 90)

zero_vol = (df['Volume'] == 0).sum()
print(f"Found {zero_vol} rows with zero volume")

if zero_vol > 0:
    # Strategy: Forward-fill volume from previous day of same ticker
    df_sorted = df.sort_values(['Ticker', 'Date']).reset_index(drop=True)

    for ticker in df['Ticker'].unique():
        ticker_mask = df_sorted['Ticker'] == ticker
        ticker_idx = df_sorted[ticker_mask].index

        for idx in ticker_idx:
            if df_sorted.loc[idx, 'Volume'] == 0:
                # Find previous non-zero volume
                prev_rows = df_sorted[(df_sorted['Ticker'] == ticker) &
                                     (df_sorted.index < idx) &
                                     (df_sorted['Volume'] > 0)]
                if len(prev_rows) > 0:
                    avg_vol = prev_rows.tail(5)['Volume'].mean()
                    df_sorted.loc[idx, 'Volume'] = max(int(avg_vol), 1000)

    df = df_sorted
    print(f"✅ Fixed by forward-filling with 5-day average volume")

    # Verify
    still_zero = (df['Volume'] == 0).sum()
    print(f"After fix: {still_zero} rows still have zero volume")

# ====== ISSUE 3: Null announcement_type (EXPECTED) ======
print("\n[3] HANDLING: Null values in announcement_type")
print("-" * 90)

null_ann = df['announcement_type'].isnull().sum()
print(f"Found {null_ann} nulls in announcement_type ({null_ann/len(df)*100:.2f}%)")
print("This is EXPECTED - most rows have no announcements")

# Fill with empty string instead of null (TFT models handle this better)
df['announcement_type'] = df['announcement_type'].fillna('none')
print("✅ Filled nulls with 'none' label")

# ====== RECALCULATE INDICATORS ======
print("\n[4] RECALCULATING: Technical indicators")
print("-" * 90)

df_sorted = df.sort_values(['Ticker', 'Date']).reset_index(drop=True)

def get_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    return 100 - (100 / (1 + (gain / (loss + 1e-9))))

for ticker in df_sorted['Ticker'].unique():
    ticker_mask = df_sorted['Ticker'] == ticker
    idx = df_sorted[ticker_mask].index

    # Recalculate indicators with fixed data
    df_sorted.loc[idx, 'sma_20'] = df_sorted.loc[idx, 'Close'].rolling(20).mean().values
    df_sorted.loc[idx, 'sma_50'] = df_sorted.loc[idx, 'Close'].rolling(50).mean().values
    df_sorted.loc[idx, 'rsi_14'] = get_rsi(df_sorted.loc[idx, 'Close']).values
    df_sorted.loc[idx, 'vol_20'] = df_sorted.loc[idx, 'Close'].pct_change().rolling(20).std().values

df = df_sorted
print("✅ Recalculated SMA-20, SMA-50, RSI-14, vol_20 with fixed prices")

# ====== SAVE CLEANED DATASET ======
print("\n[5] SAVING: Cleaned dataset")
print("-" * 90)

df.to_csv('data/processed/tft_ready.csv', index=False)
print(f"✅ Saved cleaned dataset to tft_ready.csv")

# ====== FINAL STATISTICS ======
print("\n" + "=" * 90)
print("CLEANING SUMMARY")
print("=" * 90)
print(f"Original rows:        {original_len:,}")
print(f"Final rows:           {len(df):,}")
print(f"Rows removed:         {original_len - len(df):,}")
print(f"\nData quality improvements:")
print(f"  • Close price fixes:        {outside_range}")
print(f"  • Zero volume fixes:        {zero_vol}")
print(f"  • Null handling:            {null_ann}")
print(f"\n✅ Dataset cleaned and ready for TFT training!")
print("=" * 90)
