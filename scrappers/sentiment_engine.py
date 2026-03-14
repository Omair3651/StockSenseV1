import pandas as pd
import requests
import torch
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime
from tqdm import tqdm
from ntscraper import Nitter
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ==========================================
# 1. CONFIGURATION
# ==========================================
SENTIMENT_FILE = 'data/processed/sentiment_master.csv'

TICKERS = [
    'OGDC', 'PPL', 'POL', 'HUBC', 'ENGRO', 'FFC', 'EFERT', 'LUCK', 'MCB', 'UBL',
    'HBL', 'BAHL', 'MEBL', 'NBP', 'FABL', 'BAFL', 'DGKC', 'MLCF', 'FCCL', 'CHCC',
    'PSO', 'SHEL', 'ATRL', 'PRL', 'SYS', 'SEARL', 'ILP', 'TGL', 'INIL', 'PAEL'
]

# Local Pakistan Market Keywords to override general AI
PK_LEXICON = {
    'positive': ['imf tranche', 'interest rate cut', 'cpec', 'dividend', 'surplus', 'bullish', 'recovery', 'inflow', 'profit surge', 'record high'],
    'negative': ['circular debt', 'hike', 'political instability', 'default', 'inflation', 'deficit', 'bearish', 'outflow', 'downgrade', 'penalty']
}

class CompleteSentimentScraper:
    def __init__(self):
        print("Initializing FinBERT Model...")
        self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        self.nitter = Nitter()
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        self.today = datetime.now().date()

    # Scrappers for each source
    def scrape_dawn(self):
        news = []
        try:
            r = requests.get("https://www.dawn.com/business", headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for article in soup.select('.story__title'):
                text = article.get_text(strip=True)
                if len(text) > 25:
                    news.append({'Date': self.today, 'Text': text, 'Source': 'Dawn', 'Weight': 1.2})
        except Exception as e: print(f"Dawn Scrape Failed: {e}")
        return news

    def scrape_tribune(self):
        news = []
        try:
            r = requests.get("https://tribune.com.pk/business", headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            # Tribune typically uses h2s or class 'title' for headlines
            for article in soup.find_all(['h2', 'h3']):
                text = article.get_text(strip=True)
                if len(text) > 25:
                    news.append({'Date': self.today, 'Text': text, 'Source': 'Tribune', 'Weight': 1.2})
        except Exception as e: print(f"Tribune Scrape Failed: {e}")
        return news

    def scrape_mettis(self):
        news = []
        try:
            r = requests.get("https://mettisglobal.news/category/latest-news/", headers=self.headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            # Mettis uses h3 for article titles in their lists
            for article in soup.find_all('h3'):
                text = article.get_text(strip=True)
                if len(text) > 25:
                    news.append({'Date': self.today, 'Text': text, 'Source': 'Mettis', 'Weight': 1.2})
        except Exception as e: print(f"Mettis Scrape Failed: {e}")
        return news

    def scrape_reddit(self):
        reddit_data = []
        # Public JSON endpoint (No API key required)
        urls = [
            "https://www.reddit.com/r/pakistan/search.json?q=economy OR psx OR inflation&restrict_sr=1&sort=new",
            "https://www.reddit.com/r/FIREPakistan/new.json" 
        ]
        for url in urls:
            try:
                r = requests.get(url, headers=self.headers, timeout=10)
                if r.status_code == 200:
                    posts = r.json().get('data', {}).get('children', [])
                    for post in posts[:15]: 
                        text = post['data'].get('title', '')
                        if len(text) > 15:
                            reddit_data.append({'Date': self.today, 'Text': text, 'Source': 'Reddit', 'Weight': 0.8})
            except Exception as e: print(f"Reddit Scrape Failed: {e}")
        return reddit_data

    def scrape_twitter(self):
        tweets_data = []
        try:
            # ntscraper uses public nitter instances.
            tweets = self.nitter.get_tweets("#PSX", mode='hashtag', number=50)
            if tweets and 'tweets' in tweets:
                for t in tweets['tweets']:
                    text = t['text']
                    if len(text) > 15:
                        tweets_data.append({'Date': self.today, 'Text': text, 'Source': 'Twitter', 'Weight': 0.5})
        except Exception as e: print(f"Twitter Scrape Failed: {e}")
        return tweets_data

    # ==========================================
    # 3. SENTIMENT SCORING & CATEGORIZATION
    # ==========================================
    def get_score(self, text):
        text_lower = text.lower()
        # 1. Lexicon Check
        for w in PK_LEXICON['positive']:
            if w in text_lower: return 0.85
        for w in PK_LEXICON['negative']:
            if w in text_lower: return -0.85
            
        # 2. FinBERT Check
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1).numpy()[0]
        # Label 0 is Positive, Label 1 is Negative in FinBERT
        return probs[0] - probs[1] 

    def process_all(self):
        print("--- Gathering Data from All Sources ---")
        all_raw_data = self.scrape_dawn() + self.scrape_tribune() + self.scrape_mettis() + self.scrape_reddit() + self.scrape_twitter()
        
        df = pd.DataFrame(all_raw_data)
        if df.empty:
            print("⚠️ No sentiment data collected today.")
            return

        print(f"--- Scoring {len(df)} headlines with AI & Lexicon ---")
        results = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Analyzing Sentiment"):
            base_score = self.get_score(row['Text'])
            final_score = base_score * row['Weight']
            
            # Map to specific ticker if mentioned, otherwise it is Market Macro news
            matched_ticker = "MARKET"
            for t in TICKERS:
                if t.lower() in row['Text'].lower():
                    matched_ticker = t
                    break
                    
            results.append({
                'Date': row['Date'],
                'Ticker': matched_ticker,
                'Raw_Score': round(base_score, 4),
                'Weighted_Score': round(final_score, 4),
                'Source': row['Source'],
                'Headline': row['Text'] # Keep headline for debugging/review
            })
            
        scored_df = pd.DataFrame(results)
        
        # Aggregate the average weighted sentiment per stock, per day
        daily_summary = scored_df.groupby(['Date', 'Ticker'])['Weighted_Score'].mean().reset_index()
        
        # Save to Master Sentiment File
        os.makedirs('data/processed', exist_ok=True)
        if os.path.exists(SENTIMENT_FILE):
            old_sentiment = pd.read_csv(SENTIMENT_FILE)
            old_sentiment['Date'] = pd.to_datetime(old_sentiment['Date']).dt.date
            # Append new, drop duplicates to ensure we don't duplicate a day's record
            updated_sentiment = pd.concat([old_sentiment, daily_summary]).drop_duplicates(subset=['Date', 'Ticker'], keep='last')
            updated_sentiment.to_csv(SENTIMENT_FILE, index=False)
        else:
            daily_summary.to_csv(SENTIMENT_FILE, index=False)
            
        print(f"✅ Sentiment Pipeline Complete! Appended to {SENTIMENT_FILE}")

if __name__ == "__main__":
    engine = CompleteSentimentScraper()
    engine.process_all()