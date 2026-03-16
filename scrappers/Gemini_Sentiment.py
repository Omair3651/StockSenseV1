"""
Tavily + Groq News Sentiment Scorer
====================================
Uses Tavily Search API (free: 1000 searches/month) to find news,
then Groq Llama 3.3 70B (free, no rate limits) to analyze sentiment.

Free tier costs:
  Tavily: 1,000 free searches/month (no card required)
          30 tickers/day = ~900 searches/month — fits comfortably in free tier
  Groq:   Llama 3.3 70B free tier (no documented rate limits at this volume)

Setup:
  1. Get Tavily API key (free): https://tavily.com
  2. Add TAVILY_API_KEY=tvly_... to .env
  3. Get Groq API key (free): https://console.groq.com
  4. Add GROQ_API_KEY=gsk_... to .env

Run:
    python scrappers/Gemini_Sentiment.py --ticker OGDC
    python scrappers/Gemini_Sentiment.py --all
"""

import sys
import json
import time
import re
import argparse

sys.path.insert(0, str(__file__).replace("/scrappers/Gemini_Sentiment.py", "").replace("\\scrappers\\Gemini_Sentiment.py", ""))
from config import TAVILY_API_KEY, GROQ_API_KEY, GEMINI_API_KEY_1, GEMINI_API_KEY_2, KSE30_STOCKS, COMPANY_NAMES

# ── API Clients ─────────────────────────────────────────────────────────────

def _get_tavily_client():
    """Initialise and return a Tavily client."""
    if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY not configured. Get a free key at https://tavily.com "
            "and add it to .env"
        )
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=TAVILY_API_KEY)
    except ImportError:
        raise ImportError(
            "tavily-python package not installed. Run: pip install tavily-python"
        )


def _get_groq_client():
    """Initialise and return a Groq client."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not configured. Get a free key at https://console.groq.com "
            "and add it to .env"
        )
    try:
        from groq import Groq
        return Groq(api_key=GROQ_API_KEY)
    except ImportError:
        raise ImportError(
            "groq package not installed. Run: pip install groq"
        )


def _get_gemini_client():
    """Initialise and return a Gemini client with current active key."""
    keys = [k for k in [GEMINI_API_KEY_1, GEMINI_API_KEY_2] if k]
    if not keys:
        return None, None
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=keys[0])
        return client, genai_types
    except ImportError:
        return None, None


# ── JSON extraction helper ─────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response text.
    Handles cases where LLM wraps JSON in markdown code fences.
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


# ── Core sentiment scorer ──────────────────────────────────────────────────

def _search_news(ticker: str, company_name: str) -> str:
    """
    Search for recent news about a company using Tavily.
    Returns formatted news context for sentiment analysis.
    """
    try:
        client = _get_tavily_client()

        # Search for news about this company in the last 7 days
        results = client.search(
            query=f"{company_name} {ticker} stock PSX news",
            include_answer=False,
            days=7,
            max_results=5,
        )

        # Format results into a news context string
        if not results.get("results"):
            return "No recent news found."

        news_context = []
        for i, result in enumerate(results["results"], 1):
            title = result.get("title", "")
            snippet = result.get("content", "")
            if title:
                news_context.append(f"{i}. {title}\n   {snippet[:200]}")

        return "\n".join(news_context) if news_context else "No relevant news found."

    except Exception as e:
        print(f"  [tavily] {ticker}: search error ({str(e)[:60]})")
        return None


def _analyze_sentiment(ticker: str, company_name: str, news_context: str) -> dict:
    """
    Use Groq Llama 3.3 70B to analyze sentiment from news context.
    """
    try:
        client = _get_groq_client()

        prompt = f"""You are a financial analyst for Pakistan Stock Exchange (PSX).

Analyze this news about {company_name} ({ticker}) for stock sentiment impact.

NEWS CONTEXT (last 7 days):
{news_context}

Return ONLY valid JSON:
{{"sentiment_score": float(-1.0 to 1.0), "confidence": float(0.0 to 1.0), "headline_count": int, "key_headlines": [list of headlines], "reasoning": "1 sentence"}}

Rules: 0.0 = neutral/no news. Return score: 0.0, confidence: 0.0, count: 0 if no relevant news."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )

        raw_text = response.choices[0].message.content or ""
        parsed = _extract_json(raw_text)

        if not parsed:
            print(f"  [groq] {ticker}: could not parse JSON from response")
            return None

        result = {
            "ticker":          ticker,
            "sentiment_score": float(parsed.get("sentiment_score", 0.0)),
            "confidence":      float(parsed.get("confidence", 0.0)),
            "headline_count":  int(parsed.get("headline_count", 0)),
            "key_headlines":   parsed.get("key_headlines", []),
            "reasoning":       parsed.get("reasoning", ""),
            "source":          "groq_tavily",
            "weight":          1.2,
        }
        # Clamp sentiment to [-1, 1]
        result["sentiment_score"] = max(-1.0, min(1.0, result["sentiment_score"]))
        return result

    except Exception as e:
        print(f"  [groq] {ticker}: error ({str(e)[:60]})")
        return None


def _call_gemini_fallback(ticker: str, company_name: str) -> dict:
    """
    Fallback to Gemini if Tavily+Groq fails.
    """
    try:
        client, genai_types = _get_gemini_client()
        if client is None:
            return None

        prompt = f"""You are a financial analyst for Pakistan Stock Exchange (PSX).

Analyze recent news (last 7 days) about {company_name} ({ticker}) for stock sentiment impact.

Return ONLY valid JSON:
{{"sentiment_score": float(-1.0 to 1.0), "confidence": float(0.0 to 1.0), "headline_count": int, "key_headlines": [max 3 headlines], "reasoning": "1 sentence"}}

Rules: 0.0 = neutral/no news. Return score: 0.0, confidence: 0.0, count: 0 if no relevant news."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
            return None

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
        result["sentiment_score"] = max(-1.0, min(1.0, result["sentiment_score"]))
        return result

    except Exception as e:
        print(f"  [fallback] {ticker}: error ({str(e)[:60]})")
        return None


def get_sentiment(ticker: str, company_name: str = None) -> dict:
    """
    Get sentiment for a ticker using Tavily Search + Groq analysis.
    Falls back to Gemini if primary approach fails.

    Returns:
        dict with keys:
            ticker, sentiment_score, confidence, headline_count,
            key_headlines, reasoning, source, weight
    """
    if company_name is None:
        company_name = COMPANY_NAMES.get(ticker, ticker)

    # Step 1: Search for news using Tavily
    news_context = _search_news(ticker, company_name)
    if news_context is None:
        print(f"  [fallback] {ticker}: Tavily failed, trying Gemini...")
        result = _call_gemini_fallback(ticker, company_name)
        return result if result else _neutral(ticker, error="all_providers_failed")

    # Step 2: Analyze with Groq
    result = _analyze_sentiment(ticker, company_name, news_context)
    if result:
        return result

    # Fallback to Gemini if Groq analysis fails
    print(f"  [fallback] {ticker}: Groq analysis failed, trying Gemini...")
    result = _call_gemini_fallback(ticker, company_name)
    return result if result else _neutral(ticker, error="all_providers_failed")


def _neutral(ticker: str, error: str = "") -> dict:
    return {
        "ticker":          ticker,
        "sentiment_score": 0.0,
        "confidence":      0.0,
        "headline_count":  0,
        "key_headlines":   [],
        "reasoning":       f"No data (error: {error})" if error else "No relevant news found.",
        "source":          "neutral",
        "weight":          1.0,
    }


# ── Batch scorer ───────────────────────────────────────────────────────────

def score_all_tickers(tickers: list = None, delay_seconds: float = 1.5) -> list:
    """
    Score all tickers with Tavily Search + Groq analysis.
    Adds a delay between requests as good practice.

    Args:
        tickers:       list of ticker symbols; defaults to all KSE30
        delay_seconds: sleep between API calls (1.5s is cautious)

    Returns:
        List of sentiment dicts, one per ticker.
    """
    if tickers is None:
        tickers = KSE30_STOCKS

    results = []
    for i, ticker in enumerate(tickers, 1):
        company = COMPANY_NAMES.get(ticker, ticker)
        print(f"  [{i}/{len(tickers)}] Scoring {ticker} ({company})...")
        result = get_sentiment(ticker, company)
        results.append(result)
        print(f"    source={result['source']:15} score={result['sentiment_score']:+.2f}  "
              f"conf={result['confidence']:.2f}  headlines={result['headline_count']}")
        if i < len(tickers):
            time.sleep(delay_seconds)

    return results


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSX News Sentiment Scorer (Tavily + Groq)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="Single ticker to score (e.g. OGDC)")
    group.add_argument("--all",    action="store_true", help="Score all 30 KSE tickers")
    args = parser.parse_args()

    if args.ticker:
        import sys
        import io
        # Fix Unicode output on Windows
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

        print(f"\n=== Sentiment Score: {args.ticker} ===")
        r = get_sentiment(args.ticker)
        print(f"  Source          : {r['source']}")
        print(f"  Sentiment score : {r['sentiment_score']:+.2f}")
        print(f"  Confidence      : {r['confidence']:.2f}")
        print(f"  Headlines found : {r['headline_count']}")
        print(f"  Key headlines   :")
        for h in r.get("key_headlines", []):
            print(f"    - {h}")
        print(f"  Reasoning       : {r['reasoning']}")
    else:
        import sys
        import io
        # Fix Unicode output on Windows
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

        print("\n=== Sentiment Score: All KSE30 Tickers ===")
        results = score_all_tickers()
        print(f"\nSummary: {len(results)} tickers scored")
        positive = [r for r in results if r["sentiment_score"] > 0.1]
        negative = [r for r in results if r["sentiment_score"] < -0.1]
        neutral  = [r for r in results if abs(r["sentiment_score"]) <= 0.1]
        print(f"  Positive: {len(positive)}  Negative: {len(negative)}  Neutral: {len(neutral)}")
        sources = {}
        for r in results:
            src = r["source"]
            sources[src] = sources.get(src, 0) + 1
        print(f"  Sources: {' | '.join(f'{count} {src}' for src, count in sources.items())}")
