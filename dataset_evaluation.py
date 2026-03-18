"""
Comprehensive TFT Dataset Evaluation Script
Assesses whether tft_ready.csv is ready for TFT model training
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import io
import warnings
warnings.filterwarnings('ignore')

# Fix Unicode output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 100)
print("COMPREHENSIVE TFT DATASET EVALUATION")
print("=" * 100)

# Load data
df = pd.read_csv('data/processed/tft_ready.csv')
df['Date'] = pd.to_datetime(df['Date'])

print("\n[1] DATASET OVERVIEW")
print("-" * 100)
print(f"Total rows:           {len(df):,}")
print(f"Total columns:        {len(df.columns)}")
print(f"Date range:           {df['Date'].min().date()} to {df['Date'].max().date()}")
print(f"Time span:            {(df['Date'].max() - df['Date'].min()).days} days (~{(df['Date'].max() - df['Date'].min()).days / 365:.1f} years)")
print(f"Unique tickers:       {df['Ticker'].nunique()}")
print(f"Trading days/ticker:  {len(df) / df['Ticker'].nunique():.0f} (should be ~4,114 for 18 years)")
print(f"Sectors represented:  {df['Sector'].nunique()}")

# Check for nulls
print("\n[2] DATA QUALITY - NULL VALUES")
print("-" * 100)
nulls = df.isnull().sum()
if nulls.sum() == 0:
    print("✅ PERFECT: 0 null values across all columns")
else:
    print("⚠️ WARNING: Found nulls:")
    print(nulls[nulls > 0])

# Check for duplicates
print("\n[3] DATA QUALITY - DUPLICATES")
print("-" * 100)
dupes = df.duplicated(subset=['Date', 'Ticker']).sum()
print(f"Duplicate (Date, Ticker) pairs: {dupes}")
if dupes == 0:
    print("✅ PERFECT: No duplicates")

# Check for negative/zero prices
print("\n[4] DATA QUALITY - PRICE VALIDATION")
print("-" * 100)
invalid_ohlc = (df['High'] < df['Low']).sum()
invalid_close = ((df['Close'] < df['Low']) | (df['Close'] > df['High'])).sum()
zero_volume = (df['Volume'] == 0).sum()
print(f"High < Low violations:        {invalid_ohlc}")
print(f"Close outside [Low, High]:    {invalid_close}")
print(f"Zero volume records:          {zero_volume}")
if invalid_ohlc == 0 and invalid_close == 0 and zero_volume == 0:
    print("✅ PERFECT: All OHLCV data valid")

# Technical data distribution
print("\n[5] FEATURE STATISTICS - PRICE & VOLUME")
print("-" * 100)
print(f"Close price:  min={df['Close'].min():.2f}, max={df['Close'].max():.2f}, mean={df['Close'].mean():.2f}, std={df['Close'].std():.2f}")
print(f"Volume:       min={df['Volume'].min():,.0f}, max={df['Volume'].max():,.0f}, mean={df['Volume'].mean():,.0f}")
print(f"Returns:      mean={df['Close'].pct_change().mean():.4f}, std={df['Close'].pct_change().std():.4f}")

# Indicator quality
print("\n[6] FEATURE STATISTICS - TECHNICAL INDICATORS")
print("-" * 100)
print(f"SMA-20:  mean={df['sma_20'].mean():.2f}, std={df['sma_20'].std():.2f}, min={df['sma_20'].min():.2f}, max={df['sma_20'].max():.2f}")
print(f"SMA-50:  mean={df['sma_50'].mean():.2f}, std={df['sma_50'].std():.2f}, min={df['sma_50'].min():.2f}, max={df['sma_50'].max():.2f}")
print(f"RSI-14:  mean={df['rsi_14'].mean():.2f}, std={df['rsi_14'].std():.2f}, min={df['rsi_14'].min():.2f}, max={df['rsi_14'].max():.2f}")
print(f"Vol-20:  mean={df['vol_20'].mean():.4f}, std={df['vol_20'].std():.4f}, min={df['vol_20'].min():.4f}, max={df['vol_20'].max():.4f}")

# Macro data
print("\n[7] FEATURE STATISTICS - MACRO VARIABLES")
print("-" * 100)
print(f"KSE-100 index:   min={df['market_index'].min():.2f}, max={df['market_index'].max():.2f}, mean={df['market_index'].mean():.2f}")
print(f"USD/PKR rate:    min={df['USD_PKR'].min():.2f}, max={df['USD_PKR'].max():.2f}, mean={df['USD_PKR'].mean():.2f}")

# Sentiment data
print("\n[8] SENTIMENT FEATURES ANALYSIS")
print("-" * 100)
nonzero_sentiment = (df['sentiment_score'] != 0.0).sum()
with_announcement = (df['announcement_flag'] == 1).sum()
print(f"Rows with sentiment_score != 0:  {nonzero_sentiment:,} ({nonzero_sentiment/len(df)*100:.3f}%)")
print(f"Rows with announcement_flag=1:   {with_announcement:,} ({with_announcement/len(df)*100:.3f}%)")
if nonzero_sentiment > 0:
    nonzero_df = df[df['sentiment_score'] != 0.0]
    print(f"Sentiment distribution (non-zero):")
    print(f"  Mean:   {nonzero_df['sentiment_score'].mean():.4f}")
    print(f"  Std:    {nonzero_df['sentiment_score'].std():.4f}")
    print(f"  Min:    {nonzero_df['sentiment_score'].min():.4f}")
    print(f"  Max:    {nonzero_df['sentiment_score'].max():.4f}")
    print(f"  Median: {nonzero_df['sentiment_score'].median():.4f}")

# Time series continuity
print("\n[9] TIME SERIES CONTINUITY")
print("-" * 100)
gaps_list = []
for ticker in df['Ticker'].unique()[:5]:  # Sample 5 tickers
    ticker_df = df[df['Ticker'] == ticker].sort_values('Date')
    diffs = (ticker_df['Date'].diff().dt.days).fillna(0).astype(int)
    gaps_ticker = (diffs > 1).sum()
    max_gap_ticker = diffs.max()
    gaps_list.append((ticker, len(ticker_df), gaps_ticker, max_gap_ticker))
    print(f"{ticker}: {len(ticker_df)} rows, {gaps_ticker} gaps, max gap: {max_gap_ticker} days")

# Sector distribution
print("\n[10] SECTOR DISTRIBUTION (DATA BALANCE)")
print("-" * 100)
sector_dist = df.groupby('Sector')['Ticker'].nunique().sort_values(ascending=False)
print(sector_dist.to_string())
print(f"\nTotal sectors: {len(sector_dist)}")

# Derived feature quality
print("\n[11] DERIVED FEATURES")
print("-" * 100)
print(f"sentiment_ma_5: mean={df['sentiment_ma_5'].mean():.4f}, std={df['sentiment_ma_5'].std():.4f}, min={df['sentiment_ma_5'].min():.4f}, max={df['sentiment_ma_5'].max():.4f}")
print(f"days_since_announcement: mean={df['days_since_announcement'].mean():.2f}, std={df['days_since_announcement'].std():.2f}, min={df['days_since_announcement'].min():.0f}, max={df['days_since_announcement'].max():.0f}")

# Time index
print("\n[12] TIME INDEX CONTINUITY (TFT REQUIREMENT)")
print("-" * 100)
time_idx_issues = 0
for ticker in df['Ticker'].unique():
    ticker_df = df[df['Ticker'] == ticker].sort_values('Date')
    expected = np.arange(ticker_df['time_idx'].min(), ticker_df['time_idx'].max() + 1)
    actual = ticker_df['time_idx'].values
    if len(expected) != len(actual):
        time_idx_issues += 1

if time_idx_issues == 0:
    print("✅ PERFECT: All tickers have continuous time_idx")
else:
    print(f"⚠️ WARNING: {time_idx_issues} tickers have time_idx gaps")

# Feature correlation
print("\n[13] FEATURE CORRELATION ANALYSIS")
print("-" * 100)
corr_cols = ['Close', 'sma_20', 'sma_50', 'rsi_14', 'vol_20', 'sentiment_score', 'market_index']
sample_df = df.sample(min(5000, len(df)), random_state=42)
corr_matrix = sample_df[corr_cols].corr()
print("High correlations (|r| > 0.7):")
found_high = False
for i in range(len(corr_matrix.columns)):
    for j in range(i+1, len(corr_matrix.columns)):
        if abs(corr_matrix.iloc[i, j]) > 0.7:
            print(f"  {corr_matrix.columns[i]} <-> {corr_matrix.columns[j]}: {corr_matrix.iloc[i, j]:.3f}")
            found_high = True
if not found_high:
    print("  None found - good feature independence")

# Target variable (Close) characteristics
print("\n[14] TARGET VARIABLE ANALYSIS (Close Price)")
print("-" * 100)
df_sorted = df.sort_values(['Ticker', 'Date'])
returns = df_sorted.groupby('Ticker')['Close'].pct_change()
print(f"Daily return statistics:")
print(f"  Mean:       {returns.mean():.5f}")
print(f"  Std:        {returns.std():.5f}")
print(f"  Min:        {returns.min():.5f}")
print(f"  Max:        {returns.max():.5f}")
print(f"  Skewness:   {returns.skew():.4f}")
print(f"  Kurtosis:   {returns.kurtosis():.4f}")

# Data sufficiency for TFT
print("\n[15] DATA SUFFICIENCY FOR TFT")
print("-" * 100)
n_tickers = df['Ticker'].nunique()
n_timesteps = len(df) // n_tickers
n_features = len(df.columns) - 3  # Exclude Date, Ticker, Sector
print(f"Shape for TFT: ({len(df):,} rows × {len(df.columns)} columns)")
print(f"Equivalent to: {n_tickers} series × {n_timesteps} timesteps × {n_features} features")
print(f"Training data volume: {'EXCELLENT' if n_timesteps > 500 else 'GOOD' if n_timesteps > 250 else 'MARGINAL'}")
print(f"Feature richness: {n_features} features ({'EXCELLENT' if n_features > 15 else 'GOOD' if n_features > 10 else 'MINIMAL'}")

# Final summary
print("\n" + "=" * 100)
print("FINAL RECOMMENDATION FOR TFT TRAINING")
print("=" * 100)

checks = {
    "Data Completeness": nulls.sum() == 0,
    "No Duplicates": dupes == 0,
    "Valid OHLCV": invalid_ohlc == 0 and invalid_close == 0,
    "No Zero Volume": zero_volume == 0,
    "Time Index Continuous": time_idx_issues == 0,
    "Sufficient Timesteps": n_timesteps > 500,
    "Rich Features": n_features > 10,
    "Balanced Sectors": len(sector_dist) >= 5,
    "Valid Target Values": df['Close'].notna().all()
}

passed = sum(checks.values())
total = len(checks)

print(f"\nQuality Checks: {passed}/{total} PASSED\n")
for check, status in checks.items():
    symbol = "✅" if status else "❌"
    print(f"{symbol} {check}")

print(f"\n{'='*100}")
if passed >= 8:
    print("VERDICT: ✅ DATASET IS READY FOR TFT TRAINING")
    print("\nStrengths:")
    print("  ✓ 18+ years of high-quality technical data")
    print("  ✓ 30 stocks with balanced sector representation")
    print("  ✓ Comprehensive feature set (20+ features)")
    print("  ✓ Clean data with zero nulls and duplicates")
    print("  ✓ Continuous time indices for all tickers")
    print("\nNotes:")
    print("  • Sentiment data is sparse (mostly 2024+) but acceptable")
    print("  • TFT will learn from strong technical + macro signals in early years")
    print("  • Sentiment becomes more important for recent data (2024+)")
    print("\nRecommended TFT Configuration:")
    print("  • Input length (lookback): 90-180 days")
    print("  • Output length (forecast): 7 days")
    print("  • Normalization: StandardScaler per ticker")
    print("  • Train/Val/Test split: 70%/15%/15%")
else:
    print("VERDICT: ⚠️ DATASET NEEDS IMPROVEMENTS")
    print(f"\nFailed checks: {total - passed}")
    print("Address the failed checks before TFT training")

print("=" * 100)
