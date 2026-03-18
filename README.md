# StockSense V1 - PSX Sentiment + TFT Dataset

A comprehensive platform for Pakistan Stock Exchange (PSX) sentiment analysis and Temporal Fusion Transformer (TFT) model training. Combines 18+ years of technical data with real-time and historical sentiment scores.

**Current Status:** ✅ **Phase 2 Complete** — Merged dataset ready for TFT training

---

## 🎯 Project Overview

StockSense V1 orchestrates end-to-end sentiment analysis and machine learning-ready dataset generation for 30 KSE-30 stocks:

1. **Phase 1: Data Collection** ✅
   - Technical data (2008–2026): OHLCV, indicators, macro variables
   - PSX announcements (2024–2026): official corporate events
   - Daily sentiment (Tavily+Groq): real-time news scoring

2. **Phase 2: Merge & Validation** ✅
   - Combined all three sources into unified `tft_ready.csv`
   - Fixed sentiment scoring, filled gaps, added derived features
   - Validated: 123,418 rows × 23 columns, zero nulls, all tests pass

3. **Phase 3: TFT Model** 🔄 (Planned)
   - Temporal Fusion Transformer for 7-day price forecasting
   - BUY/HOLD/SELL signals with confidence scoring

---

## 📊 Dataset Overview

### tft_ready.csv (Production Ready)
- **Shape:** 123,418 rows × 23 columns
- **Coverage:** 30 KSE-30 stocks, Jan 2008 → Mar 2026 (18+ years)
- **Quality:** 0 nulls, validated time-index continuity, no duplicates
- **Status:** ✅ Ready for TFT model training

### Input Sources

| Source | Period | Coverage | Quality |
|--------|--------|----------|---------|
| **Technical (OHLCV)** | 2008–2026 | 100% of trading days | ✅ Excellent |
| **PSX Announcements** | 2024–2026 | 435 records across 30 tickers | ✅ Official source |
| **Tavily+Groq News** | 2026-03-16 | 30 daily scores | ✅ Real-time LLM |
| **Market Macro** | 2008–2026 | KSE100 index, USD/PKR | ✅ Daily |

---

## 📁 Project Structure

```
StockSenseV1/
├── README.md                                  # This file
├── config.py                                  # Configuration: tickers, weights, paths
├── requirements.txt                           # Python dependencies
├── .gitignore                                 # Git ignore patterns
│
├── scrappers/                                 # Data collection scripts
│   ├── psx_official.py                       # PSX announcements + company pages
│   ├── technical_updater.py                  # Update OHLCV + indicators to today
│   ├── sentiment_backfill.py                 # Historical sentiment (PSX announcements)
│   ├── company_historic_announcements.py    # ⭐ NEW: Full announcement history (all months/years)
│   ├── Gemini_Sentiment.py                  # Tavily+Groq sentiment scorer (fallback)
│   └── (.claude/)                            # Internal state
│
├── pipeline.py                                # Daily sentiment pipeline orchestrator
├── merge_datasets.py                          # Phase 2: Merge + validate
│
└── data/
    ├── raw/                                   # Raw PSX data (if any)
    └── processed/
        ├── stocksense_tft_final.csv           # Technical data (123k rows)
        ├── sentiment_history.csv              # Historical sentiment (435 records)
        ├── sentiment_daily.csv                # Today's sentiment (30 rows)
        ├── sentiment_all.csv                  # Unified sentiment intermediate
        ├── company_historic_announcements.csv # ⭐ NEW: Complete announcement archive
        └── tft_ready.csv                      # ⭐ FINAL OUTPUT (ready for model)
```

---

## 🚀 Quick Start

### Complete Data Collection Workflow

**Run these scripts in order to build a complete dataset:**

```bash
# Step 1: Update technical data to today
python scrappers/technical_updater.py

# Step 2: Scrape ALL historical announcements (all months/years for each ticker)
# ⭐ This takes longer but gives you complete sentiment history
python scrappers/company_historic_announcements.py

# Step 3: Build comprehensive sentiment history from the announcements archive
python scrappers/sentiment_backfill.py --from 2008-01-01 --to 2026-03-19

# Step 4: Get today's news sentiment (Tavily+Groq)
python pipeline.py

# Step 5: Merge all sources into final training dataset
python merge_datasets.py

# Done! Your final dataset: data/processed/tft_ready.csv
```

**Time estimates:**
- Step 1 (technical update): 2-5 minutes
- Step 2 (historic announcements): 30-60 minutes (paginate through all tickers)
- Step 3 (sentiment backfill): 1-2 minutes
- Step 4 (daily sentiment): 2-3 minutes
- Step 5 (merge & validate): 1 minute

**Quick test run (on 1 ticker only):**
```bash
python scrappers/company_historic_announcements.py --ticker OGDC
python pipeline.py --ticker OGDC
python merge_datasets.py
```

---

### 1. Installation

```bash
# Clone/navigate to project
cd StockSenseV1

# Install dependencies
pip install -r requirements.txt

# Create .env file with API keys
cat > .env << EOF
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
GEMINI_API_KEY_1=optional_backup
EOF
```

### 2. Run Daily Sentiment Pipeline

```bash
# Today's sentiment for all 30 tickers (Tavily+Groq)
python pipeline.py

# Or skip news sentiment (PSX announcements only)
python pipeline.py --no-gemini

# Single ticker
python pipeline.py --ticker OGDC
```

Outputs: `data/processed/sentiment_daily.csv`

### 3. Update Technical Data

```bash
# Bring technical data to today
python scrappers/technical_updater.py
```

### 4. Merge + Validate (Creates tft_ready.csv)

```bash
# Create final TFT training dataset
python merge_datasets.py
```

Outputs: `data/processed/tft_ready.csv` ✅

---

## 📊 Data Columns (23 total)

### Technical Features (17)
| Column | Type | Source | Notes |
|--------|------|--------|-------|
| Date | datetime | PSX | YYYY-MM-DD |
| Ticker | str | PSX | KSE-30 stock symbol |
| Sector | str | Config | Banking, Energy, etc. |
| Open, High, Low, Close | float | PSX OHLCV | Stock prices (PKR) |
| Volume | int | PSX | Trading volume |
| market_index | float | Yahoo Finance | KSE-100 closing level |
| USD_PKR | float | Yahoo Finance | Exchange rate |
| day_of_week | int | Derived | 0=Mon, 6=Sun |
| month | int | Derived | 1–12 |
| sma_20, sma_50 | float | TA-Lib | 20/50-day simple moving avg |
| rsi_14 | float | TA-Lib | 14-day relative strength index |
| vol_20 | float | Derived | 20-day volatility (std of returns) |
| time_idx | int | TFT | Sequential index per ticker |

### Sentiment Features (6)
| Column | Type | Source | Notes |
|--------|------|--------|-------|
| sentiment_score | float | PSX/Tavily/Proxy | Range: [-1.0, +1.0] |
| sentiment_count | int | News articles | Number of sources |
| announcement_flag | int | PSX | 1=announcement day, 0=no news |
| announcement_type | str | PSX | dividend, earnings, rights, board, other |
| sentiment_ma_5 | float | Derived | 5-day rolling mean |
| days_since_announcement | int | Derived | Days since last flag=1 (capped at 30) |

---

## 🎯 Stocks Tracked (30 KSE-30)

| Sector | Tickers |
|--------|---------|
| **Banking** (8) | MCB, UBL, HBL, BAHL, MEBL, NBP, FABL, BAFL |
| **Energy** (3) | OGDC, PPL, POL |
| **Fertilizer** (3) | ENGRO, FFC, EFERT |
| **Cement** (5) | LUCK, DGKC, MLCF, FCCL, CHCC |
| **OMC** (2) | PSO, SHEL |
| **Refinery** (2) | ATRL, PRL |
| **Power** (1) | HUBC |
| **Pharma** (1) | SEARL |
| **Tech** (1) | SYS |
| **Textile** (1) | ILP |
| **Glass** (1) | TGL |
| **Engineering** (2) | INIL, PAEL |

---

## 🔄 Data Flow & Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   PHASE 1: COLLECTION                        │
└─────────────────────────────────────────────────────────────┘

PSX OHLCV          PSX Announcements     Tavily Search + Groq
    │                      │                       │
    └──────────────────────┼───────────────────────┘
                           │
        stocksense_tft_final.csv      sentiment_daily.csv
                           │                       │
                           └───────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              PHASE 2: MERGE & VALIDATE                      │
└─────────────────────────────────────────────────────────────┘

   Technical         +       Sentiment
   (123,418 rows)            (435 historic + 30 daily)
        │                            │
        └────────────┬───────────────┘
                     │
             [LEFT-JOIN on Date+Ticker]
                     │
             [Forward-fill & feature eng.]
                     │
              ✅ tft_ready.csv
              (123,418 rows × 23 cols)

┌─────────────────────────────────────────────────────────────┐
│              PHASE 3: TFT MODEL (PLANNED)                   │
└─────────────────────────────────────────────────────────────┘

           tft_ready.csv
                 │
        [PyTorch Forecasting]
                 │
        [TFT Model Training]
                 │
     ➜ 7-day price forecasting
     ➜ P10/P50/P90 quantiles
     ➜ BUY/HOLD/SELL signals
```

---

## 🛠️ Key Scripts & Usage

### sentiment_backfill.py
Backfill historical sentiment from PSX announcements (2024–2026).

```bash
python scrappers/sentiment_backfill.py
python scrappers/sentiment_backfill.py --ticker OGDC
python scrappers/sentiment_backfill.py --from 2024-01-01 --to 2024-12-31
```

**Output:** `data/processed/sentiment_history.csv`
- 435 records with PSX announcements + rule-based sentiment scoring
- Rule: dividend=+0.6, rights=+0.3, earnings/board/other=0.0

### company_historic_announcements.py ⭐ NEW
**Complete announcement history scraper** — Pulls ALL historical announcements for each KSE-30 stock.
Paginates through the entire PSX announcements portal by ticker, collecting every month/year.

```bash
# Full run: scrape all 30 tickers (takes ~30-60 minutes)
python scrappers/company_historic_announcements.py

# Test on first 5 tickers
python scrappers/company_historic_announcements.py --limit 5

# Single ticker
python scrappers/company_historic_announcements.py --ticker OGDC
```

**Output:** `data/processed/company_historic_announcements.csv`
- Complete archive: Symbol, Date, Time, CompanyName, Title
- Every announcement on record for each ticker
- Sorted by date (oldest to newest)
- Ready to feed into sentiment conversion

**Convert to sentiment records:**
After collecting the archive, convert to sentiment records with rule-based scoring:
```bash
python scrappers/sentiment_from_historic.py
```

**Output:** `data/processed/sentiment_history_from_archive.csv`
- Sentiment records with automatic classification (dividend/earnings/rights/board/other)
- Ready to merge into final training dataset

### sentiment_backfill.py
Backfill historical sentiment from PSX announcements (2024–2026).

```bash
python scrappers/sentiment_backfill.py
python scrappers/sentiment_backfill.py --ticker OGDC
python scrappers/sentiment_backfill.py --from 2024-01-01 --to 2024-12-31
```

**Output:** `data/processed/sentiment_history.csv`
- 435 records with PSX announcements + rule-based sentiment scoring
- Rule: dividend=+0.6, rights=+0.3, earnings/board/other=0.0

### pipeline.py
Orchestrate daily sentiment pipeline.

```bash
# Daily run (all 30 tickers)
python pipeline.py

# With PSX announcements only (skip news sentiment)
python pipeline.py --no-gemini

# Single ticker test
python pipeline.py --ticker OGDC
```

**Output:** `data/processed/sentiment_daily.csv`
- 30 rows (one per ticker) with merged PSX + news sentiment

### Gemini_Sentiment.py
Daily news sentiment scoring (fallback to Gemini if Groq fails).

```bash
# Score all 30 tickers
python scrappers/Gemini_Sentiment.py --all

# Score single ticker
python scrappers/Gemini_Sentiment.py --ticker OGDC
```

**Primary flow:** Tavily Search API → Groq Llama 3.3 70B
- Tavily: 1000 free searches/month ✅ (sufficient for 30 tickers/day)
- Groq: Free tier, no rate limits ✅

**Fallback:** Gemini Flash 2.5 (if Groq fails)
- Gemini: 15 requests/min, free tier

### merge_datasets.py ⭐
**Phase 2 Script** — Merge all three sources into final TFT dataset.

```bash
python merge_datasets.py
```

**Process:**
1. Fix sentiment scores (re-apply rule-based for PSX announcements)
2. Unify sentiment_history + sentiment_daily → sentiment_all.csv
3. Left-join with technical data on [Date, Ticker]
4. Fill gaps: forward-fill sentiment up to 5 days, then zero-fill
5. Add derived features: sentiment_ma_5, days_since_announcement
6. Validate: 8 comprehensive checks
7. Output: `data/processed/tft_ready.csv`

**Output:** `data/processed/tft_ready.csv` ✅

---

## ⚙️ Configuration

Edit [config.py](config.py) to customize:

```python
# Tickers to track (default: all 30 KSE-30)
KSE30_STOCKS = ['OGDC', 'PPL', ...]

# Sector mapping
SECTOR_MAP = {'OGDC': 'Energy', ...}

# Company names (for news search)
COMPANY_NAMES = {'OGDC': 'Oil and Gas Development Company', ...}

# Sentiment source weighting
SOURCE_WEIGHTS = {
    'psx_announcement': 2.0,    # Official PSX events (highest)
    'groq_tavily':      1.2,    # Tavily news + Groq scoring
    'gemini_news':      1.2,    # Fallback: Gemini (if Groq fails)
}
```

---

## 🔑 API Keys & Setup

### Required APIs

| API | Tier | Key | Purpose | Limit |
|-----|------|-----|---------|-------|
| **Tavily** | Free | 1000 searches/month | News retrieval | ✅ Sufficient |
| **Groq** | Free | Llama 3.3 70B | Sentiment analysis | ✅ No rate limit |
| **Yahoo Finance** | Free | yfinance lib | USD/PKR rates | ✅ Daily |

### Optional (Fallback)

| API | Tier | Key | Purpose | Limit |
|-----|------|-----|---------|-------|
| **Gemini** | Free | Flash 2.5 Lite | Sentiment fallback | 15 req/min |

### Setup .env

```bash
# Required
TAVILY_API_KEY=tvly-dev-...
GROQ_API_KEY=gsk-...

# Optional (fallback)
GEMINI_API_KEY_1=XXXXXXX...
```

All APIs used are **completely free** with generous limits.

---

## 📈 Dataset Quality Metrics

### Phase 2 Validation Results

✅ **All Checks Passed**

| Check | Result | Details |
|-------|--------|---------|
| Shape | PASS | 123,418 rows × 23 columns |
| Nulls | PASS | 0 nulls across all columns |
| Duplicates | PASS | 0 duplicate (Date, Ticker) pairs |
| Date Range | PASS | 2008-01-01 → 2026-03-16 (6,649 days) |
| Ticker Coverage | PASS | All 30 tickers present |
| Time-Index Continuity | PASS | No gaps in any ticker sequence |
| Sentiment Coverage | INFO | 0.11% non-zero (sparse but expected) |
| Announcement Coverage | INFO | 0.35% with announcement_flag=1 |

### Data Coverage by Period

| Period | Rows | Non-Zero Sentiment | With Announcements |
|--------|------|-------------------|------------------|
| 2008–2023 | 101,890 | 0.00% | 0.00% |
| 2024 | 7,220 | 0.08% | 0.32% |
| 2025 | 6,831 | 0.98% | 3.04% |
| 2026 (partial) | 1,433 | 4.19% | 13.75% |

**Note:** Sentiment data is sparse for 2008–2024 because PSX announcement archives don't go back that far. This is normal; TFT will learn from strong technical + macro signals in early period, sentiment in recent period.

---

## 🚨 Known Limitations & Future Work

### Current Limitations
1. **Historical sentiment sparse (pre-2024):** PSX archives limited to recent announcements
2. **No longer-dated sentiment on most rows:** Real news sentiment only available 2024+
3. **Proxy sentiment not implemented:** Could derive sentiment from price momentum (future optimization)

### Future Enhancements (Phase 3+)
1. ✅ TFT Model training (PyTorch Forecasting)
2. ✅ 7-day forecasting with confidence intervals
3. ✅ BUY/HOLD/SELL trading signals
4. ✅ FastAPI backend for daily predictions
5. ✅ Historical sentiment backfill from alternative news sources
6. ✅ Proxy sentiment from price/volume patterns (RSI, momentum)

---

## 🧪 Testing & Validation

### Run Tests

```bash
# Test PSX scraper
python scrappers/psx_official.py --ticker OGDC

# Test sentiment pipeline
python pipeline.py --ticker PPL

# Test data merge
python merge_datasets.py

# View final dataset
head data/processed/tft_ready.csv
wc -l data/processed/tft_ready.csv
```

### Verify Output Files

```bash
# Check all data files
ls -lh data/processed/*.csv

# Quick stats
python -c "import pandas as pd; df = pd.read_csv('data/processed/tft_ready.csv'); print(f'Shape: {df.shape}'); print(f'Nulls: {df.isnull().sum().sum()}')"
```

---

## 📋 Requirements

- **Python:** 3.8+
- **Key Libraries:**
  - pandas, numpy (data manipulation)
  - requests, beautifulsoup4, lxml (web scraping)
  - groq, tavily-python (sentiment APIs)
  - google-genai (fallback sentiment)
  - python-dotenv (configuration)
  - yfinance (macro data)
  - vaderSentiment (optional, for proxy sentiment)

See [requirements.txt](requirements.txt) for full list.

---

## 🔗 Key Files Reference

| File | Purpose |
|------|---------|
| [config.py](config.py) | Central configuration (tickers, weights, API paths) |
| [pipeline.py](pipeline.py) | Daily sentiment orchestrator |
| [merge_datasets.py](merge_datasets.py) | Phase 2: Dataset merge + validation |
| [scrappers/psx_official.py](scrappers/psx_official.py) | PSX announcements + fallback |
| [scrappers/company_historic_announcements.py](scrappers/company_historic_announcements.py) | ⭐ Complete announcement history scraper |
| [scrappers/sentiment_from_historic.py](scrappers/sentiment_from_historic.py) | Convert announcements to sentiment |
| [scrappers/sentiment_backfill.py](scrappers/sentiment_backfill.py) | Build comprehensive sentiment from announcements |
| [scrappers/technical_updater.py](scrappers/technical_updater.py) | Update OHLCV to today |
| [scrappers/Gemini_Sentiment.py](scrappers/Gemini_Sentiment.py) | News sentiment scorer |
| [.gitignore](.gitignore) | Git ignore patterns |
| [requirements.txt](requirements.txt) | Python dependencies |

---

## 📝 Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| V1.0 | Mar 2026 | ✅ Complete | Phase 1: Data collection |
| V1.1 | Mar 2026 | ✅ Complete | Phase 2: Merge + validate |
| V1.2 | Mar 19 2026 | ✅ Complete | Added comprehensive announcement scraper |
| V1.3 | TBD | 🔄 In Progress | Phase 3: TFT model training |

---

## 📧 Support & Questions

For issues, enhancements, or questions:
1. Check existing code comments
2. Review [requirements.txt](requirements.txt) for dependencies
3. Verify `.env` has all required API keys

---

**Last Updated:** March 16, 2026
**Current Phase:** Phase 2 ✅ (Merge & Validation Complete)
**Next Phase:** Phase 3 (TFT Model Training)

pip install pygooglenews newspaper3k pandas lxml requests beautifulsoup4