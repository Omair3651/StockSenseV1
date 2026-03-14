"""
Gemini News Sentiment Scorer
=============================
Uses Gemini 2.0 Flash with Google Search grounding (free tier) to:
  - Find recent news about each PSX ticker
  - Score sentiment on a -1.0 to +1.0 scale
  - Return key headlines + reasoning

Free tier limits (Google AI Studio):
  - 15 requests/minute
  - 1,000,000 tokens/day
  For 30 tickers: ~30 calls/run — well within limits.

Setup:
  1. Get a free API key at https://aistudio.google.com/apikey
  2. Add GEMINI_API_KEY=your_key to .env

Run directly to test a single ticker:
    python scrappers/news_sentiment.py --ticker OGDC
    python scrappers/news_sentiment.py --all
"""

import sys
import json
import time
import re
import argparse

sys.path.insert(0, str(__file__).replace("/scrappers/news_sentiment.py", "").replace("\\scrappers\\news_sentiment.py", ""))
from config import GEMINI_API_KEY, KSE30_STOCKS, COMPANY_NAMES

# ── Gemini client setup ────────────────────────────────────────────────────

def _get_client():
    """Initialise and return a Gemini client. Raises if key not set."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey "
            "and add it to your .env file as GEMINI_API_KEY=..."
        )
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=GEMINI_API_KEY)
        return client, genai_types
    except ImportError:
        raise ImportError(
            "google-genai package not installed. Run: pip install google-genai"
        )


# ── Prompt template ────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """
You are a financial analyst specialising in the Pakistan Stock Exchange (PSX).

Search for the latest news and developments (last 7 days) about:
Company: {company_name}
Ticker: {ticker} (listed on PSX / KSE)

Analyse the sentiment of this news specifically for its impact on the stock price.

Return ONLY a valid JSON object with exactly these fields:
{{
  "sentiment_score": <float, -1.0 (very negative) to 1.0 (very positive)>,
  "confidence": <float, 0.0 to 1.0>,
  "headline_count": <int, number of relevant news items found>,
  "key_headlines": [<up to 3 most relevant headline strings>],
  "reasoning": "<one sentence explaining the score>"
}}

Rules:
- sentiment_score of 0.0 means neutral or insufficient news
- Only include news directly relevant to this company's stock performance
- Ignore unrelated Pakistan macro news unless it specifically impacts this sector
- If no relevant news found, return sentiment_score: 0.0, confidence: 0.0, headline_count: 0
""".strip()


# ── JSON extraction helper ─────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract JSON from Gemini response text.
    Handles cases where Gemini wraps JSON in markdown code fences.
    """
    # Remove markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

    # Find the first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Last resort: try parsing the whole text
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


# ── Core scorer ────────────────────────────────────────────────────────────

def get_gemini_sentiment(ticker: str,
                         company_name: str = None,
                         retry: int = 2) -> dict:
    """
    Query Gemini 2.0 Flash with Google Search grounding for a ticker's news sentiment.

    Returns:
        dict with keys:
            ticker, sentiment_score, confidence, headline_count,
            key_headlines, reasoning, source, weight
        On failure returns neutral score (0.0) with error info.
    """
    if company_name is None:
        company_name = COMPANY_NAMES.get(ticker, ticker)

    client, genai_types = _get_client()
    prompt = _PROMPT_TEMPLATE.format(ticker=ticker, company_name=company_name)

    for attempt in range(1, retry + 2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            raw_text = response.text or ""
            parsed = _extract_json(raw_text)

            if not parsed:
                print(f"  [gemini] {ticker}: could not parse JSON from response. Raw: {raw_text[:200]!r}")
                # Return neutral on parse failure
                return _neutral(ticker, error="json_parse_failed")

            result = {
                "ticker":          ticker,
                "sentiment_score": float(parsed.get("sentiment_score", 0.0)),
                "confidence":      float(parsed.get("confidence", 0.0)),
                "headline_count":  int(parsed.get("headline_count", 0)),
                "key_headlines":   parsed.get("key_headlines", []),
                "reasoning":       parsed.get("reasoning", ""),
                "source":          "gemini_news",
                "weight":          1.2,
            }
            # Clamp sentiment to [-1, 1]
            result["sentiment_score"] = max(-1.0, min(1.0, result["sentiment_score"]))
            return result

        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                wait = 60 * attempt
                print(f"  [gemini] {ticker}: rate limit hit, waiting {wait}s...")
                time.sleep(wait)
            elif attempt <= retry:
                print(f"  [gemini] {ticker}: attempt {attempt} failed ({msg}), retrying...")
                time.sleep(5 * attempt)
            else:
                print(f"  [gemini] {ticker}: all attempts failed. Error: {msg}")
                return _neutral(ticker, error=msg[:100])

    return _neutral(ticker, error="max_retries_exceeded")


def _neutral(ticker: str, error: str = "") -> dict:
    return {
        "ticker":          ticker,
        "sentiment_score": 0.0,
        "confidence":      0.0,
        "headline_count":  0,
        "key_headlines":   [],
        "reasoning":       f"No data (error: {error})" if error else "No relevant news found.",
        "source":          "gemini_news",
        "weight":          1.2,
    }


# ── Batch scorer ───────────────────────────────────────────────────────────

def score_all_tickers(tickers: list[str] = None,
                      delay_seconds: float = 4.5) -> list[dict]:
    """
    Score all tickers with Gemini.
    Adds a delay between requests to stay within the free tier (15 req/min).

    Args:
        tickers:       list of ticker symbols; defaults to all KSE30
        delay_seconds: sleep between API calls (4.5s → ~13 req/min, safely under 15)

    Returns:
        List of sentiment dicts, one per ticker.
    """
    if tickers is None:
        tickers = KSE30_STOCKS

    results = []
    for i, ticker in enumerate(tickers, 1):
        company = COMPANY_NAMES.get(ticker, ticker)
        print(f"  [{i}/{len(tickers)}] Scoring {ticker} ({company})...")
        result = get_gemini_sentiment(ticker, company)
        results.append(result)
        print(f"    score={result['sentiment_score']:+.2f}  "
              f"conf={result['confidence']:.2f}  "
              f"headlines={result['headline_count']}  "
              f"reason: {result['reasoning'][:80]}")
        if i < len(tickers):
            time.sleep(delay_seconds)

    return results


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini PSX News Sentiment Scorer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="Single ticker to score (e.g. OGDC)")
    group.add_argument("--all",    action="store_true", help="Score all 30 KSE tickers")
    args = parser.parse_args()

    if args.ticker:
        print(f"\n=== Gemini Sentiment: {args.ticker} ===")
        r = get_gemini_sentiment(args.ticker)
        print(f"  Sentiment score : {r['sentiment_score']:+.2f}")
        print(f"  Confidence      : {r['confidence']:.2f}")
        print(f"  Headlines found : {r['headline_count']}")
        print(f"  Key headlines   :")
        for h in r.get("key_headlines", []):
            print(f"    - {h}")
        print(f"  Reasoning       : {r['reasoning']}")
    else:
        print("\n=== Gemini Sentiment: All KSE30 Tickers ===")
        results = score_all_tickers()
        print(f"\nSummary: {len(results)} tickers scored")
        positive = [r for r in results if r["sentiment_score"] > 0.1]
        negative = [r for r in results if r["sentiment_score"] < -0.1]
        neutral  = [r for r in results if abs(r["sentiment_score"]) <= 0.1]
        print(f"  Positive: {len(positive)}  Negative: {len(negative)}  Neutral: {len(neutral)}")
