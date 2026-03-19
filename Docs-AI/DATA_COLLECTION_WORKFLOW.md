# 📊 Complete Data Collection Workflow - Phase 2 Enhanced

## What You Now Have

Your codebase can now collect **ALL historical PSX company announcements** for every KSE-30 stock and convert them to sentiment records. This enables a complete, dense historical dataset.

---

## The 3-Layer Data Collection Pipeline

### Layer 1: Technical Data (✅ Complete)
- **File:** `data/processed/stocksense_tft_final.csv` (123,418 rows)
- **Coverage:** 2008-2026 daily OHLCV + indicators + macro
- **Updater:** `scrappers/technical_updater.py`
- **Status:** Strong, no gaps

### Layer 2: Historical Announcements (🆕 NEW)
- **File:** `data/processed/company_historic_announcements.csv`  
- **Coverage:** Complete PSX announcement history (ALL months/years for each ticker)
- **Scraper:** `scrappers/company_historic_announcements.py`
- **Conversion:** `scrappers/sentiment_from_historic.py`
- **Output:** `data/processed/sentiment_history_from_archive.csv`
- **Status:** Comprehensive, paginated through entire PSX portal

### Layer 3: Daily News Sentiment (✅ Complete)
- **File:** `data/processed/sentiment_daily.csv` (30 rows/day)
- **Coverage:** Today's sentiment for each ticker from Tavily+Groq
- **Runner:** `pipeline.py`
- **Status:** Real-time, updated daily

---

## Step-by-Step Execution Plan

### ✅ Step 1: Setup (One Time)
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env with API keys
cat > .env << EOF
GROQ_API_KEY=gsk_...
TAVILY_API_KEY=tvly-...
GEMINI_API_KEY_1=...  # optional
EOF
```

### ✅ Step 2: Update Technical Data
```bash
python scrappers/technical_updater.py
# Time: 2-5 minutes
# Output: Updates data/processed/stocksense_tft_final.csv to today's date
```

### 🆕 Step 3: Scrape ALL Historical Announcements (NEW!)
```bash
# Full production run (all 30 tickers, ~30-60 minutes)
python scrappers/company_historic_announcements.py

# Or quick test (first 5 tickers only)
python scrappers/company_historic_announcements.py --limit 5

# Or single ticker test
python scrappers/company_historic_announcements.py --ticker OGDC
```

**Output:** `data/processed/company_historic_announcements.csv`
- Columns: `Symbol, Date, Time, CompanyName, Title`
- Example:
  ```
  OGDC,2024-03-15,10:30 AM,Oil and Gas Development Company,Board Meeting
  OGDC,2024-02-20,2:15 PM,Oil and Gas Development Company,Dividend Announcement
  ```

### 🆕 Step 4: Convert Archive to Sentiment Records (NEW!)
```bash
python scrappers/sentiment_from_historic.py
# Time: <1 minute
```

**Output:** `data/processed/sentiment_history_from_archive.csv`
- Complete sentiment history with automatic classification
- Rule-based scoring (dividend +0.6, rights +0.3, earnings/board/other 0.0)
- Covers entire PSX history from your data

### ✅ Step 5: Get Today's News Sentiment
```bash
python pipeline.py
# Time: 2-3 minutes
# Combines PSX announcements + Tavily+Groq news scoring
```

**Output:** `data/processed/sentiment_daily.csv`
- 30 rows (one per ticker) with today's merged sentiment

### ✅ Step 6: Final Merge & Validation
```bash
python merge_datasets.py
# Time: 1 minute
```

**Output:** `data/processed/tft_ready.csv`
- ✅ 123,418 rows × 23 columns
- ✅ 0 nulls, no duplicates
- ✅ Ready for TFT model training

---

## What Each CSV Contains

| File | Rows | Columns | Use |
|------|------|---------|-----|
| `company_historic_announcements.csv` | ~100k+ | Symbol, Date, Time, CompanyName, Title | Raw announcement archive |
| `sentiment_history_from_archive.csv` | ~100k+ | Date, Ticker, sentiment_score, announcement_flag, ... | Historical sentiment |
| `sentiment_daily.csv` | 30 | Date, Ticker, sentiment_score, ... | Today's sentiment |
| `stocksense_tft_final.csv` | 123,418 | Date, Ticker, Open, Close, ..., time_idx | Technical + macro |
| **`tft_ready.csv`** | **123,418** | All 23 columns (technical + sentiment) | **FINAL TRAINING DATA** |

---

## Timeline Estimates

| Step | Command | Time |
|------|---------|------|
| 1 | Setup (one-time) | 5 min |
| 2 | `technical_updater.py` | 2-5 min |
| 3 | `company_historic_announcements.py` (full) | 30-60 min |
| 4 | `sentiment_from_historic.py` | <1 min |
| 5 | `pipeline.py` | 2-3 min |
| 6 | `merge_datasets.py` | 1 min |
| **TOTAL** | **Full workflow** | **45-75 min** |

**Quick test (to verify everything works):**
```bash
# Run on just 1 ticker — 5 minutes total
scrappers/company_historic_announcements.py --ticker OGDC
python scrappers/sentiment_from_historic.py
python pipeline.py --ticker OGDC
python merge_datasets.py
```

---

## After You Have tft_ready.csv

Your dataset is now ready for Phase 3: **TFT Model Training**

The dataset contains:
- ✅ **18+ years** of historical price data
- ✅ **Dense sentiment signals** from historic announcements
- ✅ **Today's market data + news sentiment**
- ✅ **All 30 KSE-30 stocks** in one unified table
- ✅ **No nulls, no duplicates**, fully validated

Next: Train a Temporal Fusion Transformer (TFT) model to:
1. Learn patterns from past price + sentiment + technical indicators
2. Predict future returns (1-day, 7-day)
3. Generate BUY/HOLD/SELL signals with confidence scores

---

## Optional: Daily Production Loop

Once trained, run each day (automatically via scheduler):

```bash
# 6:00 PM - Update prices
python scrappers/technical_updater.py

# 6:15 PM - Today's sentiment
python pipeline.py

# 6:30 PM - Rebuild features
python merge_datasets.py

# 6:45 PM - Run inference (your trained model)
# python models/predict.py  # (Phase 3)

# 7:00 PM - Publish signals
# Ticker | Expected_Return | BUY/HOLD/SELL | Confidence
```

---

## Key Insight: Why This Matters

**Before:** You had sparse historical sentiment (only 2024+ coverage)  
**After:** You have complete historical sentiment from the PSX archive

This means:
- Your model can learn sentiment-price relationships across **18+ years**, not just 2 years
- Rare events (large dividends, earnings surprises) are captured with full context
- More robust signal for retraining and model evaluation

---

## Troubleshooting

**Q: Step 3 (announcements scraper) is slow / timing out**  
A: PSX portal has pagination delays. Normal for 30 tickers × 100+ pages each. Use `--ticker OGDC` to test single ticker first.

**Q: Step 4 (sentiment conversion) shows fewer rows than Step 3**  
A: This is expected — we only count actual announcement records, some rows may be duplicates that are deduplicated.

**Q: Step 6 (merge) shows validation errors**  
A: Check your `.env` file has all API keys. Run `python scrappers/Gemini_Sentiment.py --ticket OGDC` to debug sentiment scorer.

**Q: How long does the full workflow take?**  
A: ~1 hour. Step 3 (scraping) is the longest. You can run it overnight.

---

**Next:** Ready to train your TFT model? 🚀
