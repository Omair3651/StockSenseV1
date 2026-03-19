"""
Run PSX Announcement Sentiment Analyzer
Usage: python run_announcements.py
Reads:  data/raw/company_historic_announcements.csv
Writes: data/Sentiment Ready/company announcements sentiment.csv
"""

import os
import sys
import csv

# ── Make sure the analyzer module is findable ─────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from rulebased import analyze

# ── Paths ─────────────────────────────────────────────────────────────────────
INPUT_PATH  = os.path.join("data", "raw", "company_historic_announcements.csv")
OUTPUT_DIR  = os.path.join("data", "Sentiment Ready")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "company announcements sentiment.csv")

# ── Validate input ────────────────────────────────────────────────────────────
if not os.path.exists(INPUT_PATH):
    print(f"ERROR: Input file not found: {INPUT_PATH}")
    print("Make sure you run this script from your project root directory.")
    sys.exit(1)

# ── Create output directory ───────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Detect column names ───────────────────────────────────────────────────────
with open(INPUT_PATH, newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    original_cols = reader.fieldnames or []
    first_row = next(reader, None)

print(f"Input columns: {original_cols}")

# Auto-detect title and symbol columns
TITLE_COL  = next((c for c in original_cols if 'title' in c.lower()), None)
SYMBOL_COL = next((c for c in original_cols if c.lower() in ('symbol','ticker','code','scrip')), None)

if not TITLE_COL:
    print(f"ERROR: Could not find a 'title' column. Available: {original_cols}")
    sys.exit(1)

print(f"Title column:  '{TITLE_COL}'")
print(f"Symbol column: '{SYMBOL_COL}' (optional)")

# ── New output columns ────────────────────────────────────────────────────────
NEW_COLS = [
    'sentiment_label',
    'sentiment_score',
    'sentiment_category',
    'sentiment_sub_category',
    'sentiment_explanation',
    'sentiment_flags',
]

# ── Process ───────────────────────────────────────────────────────────────────
with open(INPUT_PATH, newline='', encoding='utf-8-sig') as f_in:
    reader = csv.DictReader(f_in)
    rows = list(reader)

total = len(rows)
print(f"\nProcessing {total:,} announcements...")

results = []
label_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

for i, row in enumerate(rows, 1):
    title  = row.get(TITLE_COL, '').strip()
    symbol = row.get(SYMBOL_COL, '').strip() if SYMBOL_COL else ''

    result = analyze(title, symbol)

    out_row = dict(row)
    out_row['sentiment_label']       = result.label
    out_row['sentiment_score']       = round(result.score, 4)
    out_row['sentiment_category']    = result.category
    out_row['sentiment_sub_category']= result.sub_category
    out_row['sentiment_explanation'] = result.explanation
    out_row['sentiment_flags']       = '|'.join(result.flags)

    results.append(out_row)
    label_counts[result.label] += 1

    if i % 2000 == 0 or i == total:
        pct = i / total * 100
        print(f"  {i:>6,} / {total:,}  ({pct:.1f}%)  "
              f"pos={label_counts['positive']:,}  "
              f"neu={label_counts['neutral']:,}  "
              f"neg={label_counts['negative']:,}")

# ── Write output ──────────────────────────────────────────────────────────────
out_cols = original_cols + NEW_COLS

with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8-sig') as f_out:
    writer = csv.DictWriter(f_out, fieldnames=out_cols)
    writer.writeheader()
    writer.writerows(results)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  Done! Output saved to:")
print(f"  {OUTPUT_PATH}")
print(f"{'='*55}")
print(f"  Total rows   : {total:,}")
print(f"  Positive     : {label_counts['positive']:,}  ({label_counts['positive']/total*100:.1f}%)")
print(f"  Neutral      : {label_counts['neutral']:,}  ({label_counts['neutral']/total*100:.1f}%)")
print(f"  Negative     : {label_counts['negative']:,}  ({label_counts['negative']/total*100:.1f}%)")
print(f"{'='*55}")