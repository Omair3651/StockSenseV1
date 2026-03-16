import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SENTIMENT_CSV = DATA_DIR / "sentiment_daily.csv"
TFT_CSV       = DATA_DIR / "stocksense_tft_final.csv"
TFT_READY_CSV = DATA_DIR / "tft_ready.csv"

# ── API Keys ───────────────────────────────────────────────────────────────
GEMINI_API_KEY_1 = os.getenv("GEMINI_API_KEY_1", "")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "")
# Fallback to single key if only one is provided
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY_1)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ── Stocks ─────────────────────────────────────────────────────────────────
KSE30_STOCKS = [
    'OGDC', 'PPL', 'POL', 'HUBC', 'ENGRO', 'FFC', 'EFERT', 'LUCK', 'MCB', 'UBL',
    'HBL', 'BAHL', 'MEBL', 'NBP', 'FABL', 'BAFL', 'DGKC', 'MLCF', 'FCCL', 'CHCC',
    'PSO', 'SHEL', 'ATRL', 'PRL', 'SYS', 'SEARL', 'ILP', 'TGL', 'INIL', 'PAEL'
]

SECTOR_MAP = {
    'OGDC': 'Energy',    'PPL': 'Energy',    'POL': 'Energy',    'HUBC': 'Power',
    'ENGRO': 'Fertilizer', 'FFC': 'Fertilizer', 'EFERT': 'Fertilizer',
    'LUCK': 'Cement',   'DGKC': 'Cement',   'MLCF': 'Cement',
    'FCCL': 'Cement',   'CHCC': 'Cement',
    'MCB': 'Banking',   'UBL': 'Banking',   'HBL': 'Banking',
    'BAHL': 'Banking',  'MEBL': 'Banking',  'NBP': 'Banking',
    'FABL': 'Banking',  'BAFL': 'Banking',
    'PSO': 'OMC',       'SHEL': 'OMC',
    'ATRL': 'Refinery', 'PRL': 'Refinery',
    'SYS': 'Tech',      'SEARL': 'Pharma',  'ILP': 'Textile',
    'TGL': 'Glass',     'INIL': 'Engineering', 'PAEL': 'Engineering'
}

# Full company names — used in Gemini search queries for better results
COMPANY_NAMES = {
    'OGDC':  'Oil and Gas Development Company',
    'PPL':   'Pakistan Petroleum Limited',
    'POL':   'Pakistan Oilfields Limited',
    'HUBC':  'Hub Power Company',
    'ENGRO': 'Engro Corporation',
    'FFC':   'Fauji Fertilizer Company',
    'EFERT': 'Engro Fertilizers',
    'LUCK':  'Lucky Cement',
    'MCB':   'MCB Bank',
    'UBL':   'United Bank Limited',
    'HBL':   'Habib Bank Limited',
    'BAHL':  'Bank AL Habib',
    'MEBL':  'Meezan Bank',
    'NBP':   'National Bank of Pakistan',
    'FABL':  'Faysal Bank',
    'BAFL':  'Bank Alfalah',
    'DGKC':  'D.G. Khan Cement',
    'MLCF':  'Maple Leaf Cement',
    'FCCL':  'Fauji Cement',
    'CHCC':  'Cherat Cement',
    'PSO':   'Pakistan State Oil',
    'SHEL':  'Shell Pakistan',
    'ATRL':  'Attock Refinery',
    'PRL':   'Pakistan Refinery Limited',
    'SYS':   'Systems Limited',
    'SEARL': 'Searle Company',
    'ILP':   'International Leather Processing',
    'TGL':   'Tariq Glass Industries',
    'INIL':  'International Industries Limited',
    'PAEL':  'Pak Elektron Limited',
}

# Scraper settings
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}
REQUEST_TIMEOUT = 20

# Announcement type → base sentiment score (rule-based fallback)
ANNOUNCEMENT_SCORES = {
    'dividend':    0.60,
    'earnings':    0.0,   # Gemini will determine positive/negative from text
    'rights':      0.30,
    'board':       0.0,
    'other':       0.0,
}

# Source weights for final sentiment aggregation
SOURCE_WEIGHTS = {
    'psx_announcement': 2.0,
    'psx_company':      1.5,
    'gemini_news':      1.2,
    'groq_compound':    1.2,
    'groq_tavily':      1.2,
}
