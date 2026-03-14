# StockSense V2 - PSX Sentiment + TFT Prediction System

## Overview

StockSense V2 is a next-generation platform for Pakistan Stock Exchange (PSX) analysis. It combines:

1. **Reworked Sentiment Engine** — Scrapes PSX official announcements + Gemini 2.5 Flash grounded search for real-time news sentiment
2. **Temporal Fusion Transformer (TFT)** — Deep learning model for 7-day stock price forecasting with BUY/HOLD/SELL signals (coming soon)
3. **TFT-Ready Dataset** — 18-feature technical + sentiment data merged into a single training file

## Project Structure

```
StockSenseV2/
├── config.py                           # Configuration: tickers, sectors, API keys, paths
├── scrappers/
│   ├── psx_official.py                 # PSX announcements + company pages
│   └── news_sentiment.py               # Gemini 2.5 Flash grounded search scorer
├── pipeline.py                         # Orchestrator: daily run + backfill
├── data/processed/
│   ├── stocksense_tft_final.csv        # Technical data (2008–2025, 123K rows)
│   ├── sentiment_daily.csv             # OUTPUT: daily sentiment scores
│   └── tft_ready.csv                   # Final merged technical + sentiment
└── old_model/                          # Legacy LSTM+LightGBM+XGBoost (reference)
```

## Data Sources

### PSX Official (Weight: 2.0)
- **Announcements** — `dps.psx.com.pk/announcements`
  - Corporate events: dividends, earnings, rights issues, board notices
  - Ticker-attributed automatically
- **Company Pages** — `dps.psx.com.pk/company/<TICKER>`
  - Financial highlights, sector info, key ratios

### Gemini 2.5 Flash News (Weight: 1.2)
- Free via Google AI Studio (no credit card, no expiry)
- Google Search grounding — finds live PSX news automatically
- Scores sentiment -1.0 (very negative) to +1.0 (very positive)
- Returns key headlines + reasoning

## Installation

### 1. Clone/Navigate to Project
```bash
cd StockSenseV2
```

### 2. Install Dependencies
```bash
pip install pandas requests beautifulsoup4 lxml google-genai python-dotenv
```

### 3. Get Gemini API Key (Free)
1. Visit `https://aistudio.google.com/apikey`
2. Create a free API key
3. Add to `.env` file:
```
GEMINI_API_KEY=your_key_here
```

## Usage

### Test PSX Official Scraper (no API key needed)
```bash
python scrappers/psx_official.py --ticker OGDC
```
Shows PSX announcements for OGDC with classification (dividend/earnings/rights/board).

### Test Gemini Scorer
```bash
python scrappers/news_sentiment.py --ticker OGDC
```
Queries Gemini for recent OGDC news and returns sentiment score + key headlines.

### Run Daily Sentiment Pipeline (all 30 tickers)
```bash
python pipeline.py
```
Outputs: `data/processed/sentiment_daily.csv` with columns:
- `Date`, `Ticker`, `sentiment_score` (-1 to 1), `sentiment_count`, `announcement_flag`, `announcement_type`

### Backfill Historical PSX Announcements (one-time)
```bash
python pipeline.py --backfill --from 2022-01-01 --to 2024-12-31
```
Scrapes PSX announcements for the date range (no Gemini — only covers recent dates).

### Single Ticker Test
```bash
python pipeline.py --ticker OGDC
```

### Skip Gemini (faster testing)
```bash
python pipeline.py --no-gemini
```

## Features

### ✅ Fixed Sentiment Engine

| Issue (V1) | Fix (V2) |
|---|---|
| Nitter dead | Removed entirely — use Gemini's Google Search |
| No PSX data | Added `dps.psx.com.pk/announcements` (highest signal) |
| Broken lexicon | Lexicon now additive (±0.15–0.25 adjustment), not override |
| No ticker attribution | PSX announcements are ticker-specific; Gemini scores per ticker |
| No backfill | Full historical PSX announcement scraper included |
| Not merged | `pipeline.py` produces `tft_ready.csv` for model training |

### 📊 Sentiment Output Schema

**sentiment_daily.csv:**
```
Date,Ticker,sentiment_score,sentiment_count,announcement_flag,announcement_type,key_headlines,reasoning
2026-03-14,OGDC,-0.2000,6,1,earnings,"['OGDC profit down 19% in FY25', '...']","Negative profit news outweighs positive buying interest"
2026-03-14,PPL,0.3500,4,0,other,"['PPL sees heavy buying interest', '...']","Positive investor sentiment"
```

### 🎯 TFT Ready Data

**tft_ready.csv** (merged technical + sentiment):
- All 18 original technical columns: `Date, Open, High, Low, Close, Volume, Ticker, market_index, USD_PKR, Sector, day_of_week, month, sma_20, sma_50, rsi_14, vol_20, time_idx`
- Plus sentiment columns: `sentiment_score, announcement_flag`
- No null rows — ready for PyTorch Forecasting TFT model training

## Stocks Tracked (30 KSE-30)

**Energy:** OGDC, PPL, POL, PSO, SHEL, ATRL, PRL
**Banking:** MCB, UBL, HBL, BAHL, MEBL, NBP, FABL, BAFL
**Fertilizer:** ENGRO, FFC, EFERT
**Cement:** LUCK, DGKC, MLCF, FCCL, CHCC
**Power:** HUBC
**Pharma:** SEARL
**Refinery:** ATRL, PRL
**Tech:** SYS
**Textile:** ILP
**Glass:** TGL
**Engineering:** INIL, PAEL
**OMC:** PSO, SHEL

## Configuration

### Edit Tickers and Sectors
File: [config.py](config.py)
```python
KSE30_STOCKS = ['OGDC', 'PPL', ...]
SECTOR_MAP = {'OGDC': 'Energy', ...}
COMPANY_NAMES = {'OGDC': 'Oil and Gas Development Company', ...}
```

### Adjust Source Weights
```python
SOURCE_WEIGHTS = {
    'psx_announcement': 2.0,
    'psx_company':      1.5,
    'gemini_news':      1.2,
}
```

## Architecture

### Data Flow
```
PSX Announcements     Gemini Search     PSX Company Pages
        │                  │                    │
        └──────────────┬───┴────────────────────┘
                       │
              [pipeline.py orchestrator]
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    Deduplicate    Aggregate      Merge weights
         │             │             │
         └─────────────┼─────────────┘
                       │
              sentiment_daily.csv
                       │
         ┌─────────────┴──────────────┐
         │                            │
    stocksense_tft_final.csv     [LEFT JOIN on Date+Ticker]
         │                            │
         └─────────────┬──────────────┘
                       │
                 tft_ready.csv (for TFT training)
```

### Sentiment Scoring Formula
```
final_score = (psx_score × 2.0 + gemini_score × 1.2) / (2.0 + 1.2)
  clamped to [-1.0, 1.0]
```

For days with no announcement but Gemini news: Gemini dominates.
For days with announcement + Gemini news: Weighted average.

## Requirements

- Python 3.8+
- pandas, numpy, requests, beautifulsoup4, lxml
- google-genai (Gemini 2.5 Flash API)
- python-dotenv

**No paid APIs.** Gemini API is completely free via Google AI Studio.

## Next Steps (Coming Soon)

1. **TFT Model Training** — PyTorch Forecasting with 18 features (15 technical + 3 sentiment)
2. **7-Day Forecasting** — P10/P50/P90 quantile predictions
3. **BUY/HOLD/SELL Signals** — Confidence-weighted trading recommendations
4. **FastAPI Backend** — REST API for predictions + daily automation

## Notes

- First run of `pipeline.py --backfill` takes ~10–20 min to scrape 2+ years of PSX announcements
- Daily `pipeline.py` run: ~3 min for all 30 tickers (includes Gemini delays to stay within free tier)
- Gemini free tier: 15 requests/min, 1M tokens/day — sufficient for 30 tickers/day
- PSX announcements endpoint may have intermittent rate-limiting; script retries automatically
- `.env` file with `GEMINI_API_KEY` is required to run Gemini scorer

## Legacy Version

Old model (LSTM + LightGBM + XGBoost ensemble) saved in `old_model/` folder with full documentation.
Reference: [old_model/README.md](old_model/README.md)

## License

Proprietary - StockSense V2

---

**Last Updated**: March 2026
**Current Version**: V2.0 (Sentiment Engine + TFT Data Pipeline)
