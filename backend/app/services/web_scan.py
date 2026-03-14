# Scans the web for plagiarism using DuckDuckGo — no API key needed.
# Flow: extract key phrases → search DDG → fetch pages → score similarity → return matches.

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from app.services.fuzzy import jaccard_similarity, ngram_similarity, levenshtein_similarity
from app.services.preprocess import preprocess_text


# bs4 is needed to parse fetched pages
try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

# prefer the new `ddgs` package, fall back to the old name if not yet updated
try:
    from ddgs import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        _DDG_AVAILABLE = True
    except ImportError:
        _DDG_AVAILABLE = False


_EXECUTOR = ThreadPoolExecutor(max_workers=4)


@dataclass
class WebMatch:
    url: str
    title: str
    snippet: str        # short excerpt from DDG
    page_excerpt: str   # best-matching chunk pulled from the actual page
    similarity_scores: dict = field(default_factory=dict)
    best_score: float = 0.0
    is_plagiarism: bool = False


@dataclass
class WebScanResult:
    submitted_text: str
    matches: List[WebMatch] = field(default_factory=list)
    is_plagiarism: bool = False
    best_score: float = 0.0
    best_url: Optional[str] = None
    total_urls_checked: int = 0
    error: Optional[str] = None


def extract_search_queries(text: str, max_queries: int = 3, min_words: int = 6) -> List[str]:
    """Pick the longest sentences from the text to use as search queries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    valid = [s.strip() for s in sentences if len(s.split()) >= min_words]

    if not valid:
        # no proper sentences — split into 8-word chunks instead
        words = text.split()
        valid = [" ".join(words[i:i + 8]) for i in range(0, len(words), 8)]

    valid.sort(key=len, reverse=True)
    return valid[:max_queries]


# browser-like headers to avoid being blocked when fetching pages
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _search_ddg_sync(query: str, max_results: int = 10) -> List[dict]:
    """Run a DuckDuckGo text search and return results as {href, title, body} dicts."""
    if not _DDG_AVAILABLE:
        raise RuntimeError("ddgs not installed. Run: pip install ddgs")

    try:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results)
    except Exception as e:
        raise RuntimeError(f"DuckDuckGo search failed: {e}")

    return [
        {"href": item.get("href", ""), "title": item.get("title", ""), "body": item.get("body", "")}
        for item in (raw or [])
    ]


def _fetch_page_text_sync(url: str, timeout: int = 8) -> str:
    """Download a page and return its visible text, stripped of navigation/scripts."""
    if not _BS4_AVAILABLE:
        return ""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    except Exception:
        return ""


def _windowed_similarity(query: str, page_text: str) -> dict:
    """
    Score similarity between the query and the most similar window of the page.
    Sliding windows prevent long pages from being unfairly penalised.
    """
    q_words = query.split()
    p_words = page_text.split()

    window = max(len(q_words) * 2, 50)
    step = max(window // 3, 20)

    best = {"levenshtein": 0.0, "jaccard": 0.0, "ngram": 0.0}

    segments = (
        [page_text]
        if len(p_words) <= window
        else [" ".join(p_words[i: i + window]) for i in range(0, len(p_words) - window + 1, step)]
    )

    pq = preprocess_text(query)
    for segment in segments:
        ps = preprocess_text(segment)
        if not pq or not ps:
            continue

        best["jaccard"] = max(best["jaccard"], round(jaccard_similarity(pq, ps), 3))
        best["ngram"] = max(best["ngram"], round(ngram_similarity(pq, ps, n=3), 3))
        # skip levenshtein on large segments — too slow
        if len(pq) <= 400 and len(ps) <= 400:
            best["levenshtein"] = max(best["levenshtein"], round(levenshtein_similarity(pq, ps), 3))

    return best


def _best_matching_excerpt(query: str, page_text: str, char_limit: int = 300) -> str:
    """Return the page chunk with the most word overlap with the query."""
    q_words = set(preprocess_text(query).split())
    p_words = page_text.split()
    window = max(len(q_words) * 2, 40)
    step = max(window // 3, 15)

    best_excerpt = page_text[:char_limit]
    best_overlap = 0

    for i in range(0, max(1, len(p_words) - window + 1), step):
        chunk = p_words[i: i + window]
        overlap = len(q_words & set(chunk))
        if overlap > best_overlap:
            best_overlap = overlap
            best_excerpt = " ".join(chunk)[:char_limit]

    return best_excerpt


async def scan_text_online(
    text: str,
    threshold: float = 0.5,
    max_queries: int = 3,
    max_results_per_query: int = 5,
) -> WebScanResult:
    """Search the web for the given text and return all sources that cross the similarity threshold."""
    if not _DDG_AVAILABLE:
        return WebScanResult(submitted_text=text, error="ddgs not installed. Run: pip install ddgs")
    if not _BS4_AVAILABLE:
        return WebScanResult(submitted_text=text, error="beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml")

    loop = asyncio.get_event_loop()
    queries = extract_search_queries(text, max_queries=max_queries)

    seen_urls: set = set()
    search_results: list = []

    for query in queries:
        try:
            raw = await loop.run_in_executor(_EXECUTOR, _search_ddg_sync, query, max_results_per_query)
        except RuntimeError as e:
            return WebScanResult(submitted_text=text, error=str(e))
        for r in raw:
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                search_results.append(r)

    total_checked = len(search_results)

    async def _process(result_dict: dict) -> Optional[WebMatch]:
        url = result_dict.get("href", "")
        title = result_dict.get("title", "")
        snippet = result_dict.get("body", "")

        page_text = await loop.run_in_executor(_EXECUTOR, _fetch_page_text_sync, url)
        comparison_text = page_text if page_text else snippet
        if not comparison_text:
            return None

        scores = _windowed_similarity(text, comparison_text)
        best_score = max(scores.values())
        if best_score < threshold:
            return None

        return WebMatch(
            url=url,
            title=title,
            snippet=snippet[:300],
            page_excerpt=_best_matching_excerpt(text, page_text) if page_text else snippet[:300],
            similarity_scores=scores,
            best_score=round(best_score, 4),
            is_plagiarism=True,
        )

    raw_results = await asyncio.gather(*[_process(r) for r in search_results], return_exceptions=True)
    matches = sorted(
        [r for r in raw_results if isinstance(r, WebMatch)],
        key=lambda m: m.best_score,
        reverse=True,
    )

    return WebScanResult(
        submitted_text=text,
        matches=matches,
        is_plagiarism=len(matches) > 0,
        best_score=matches[0].best_score if matches else 0.0,
        best_url=matches[0].url if matches else None,
        total_urls_checked=total_checked,
    )


async def scan_texts_online(
    texts: List[str],
    threshold: float = 0.5,
    max_queries: int = 2,
    max_results_per_query: int = 5,
) -> List[WebScanResult]:
    """Run scan_text_online on multiple texts concurrently."""
    return await asyncio.gather(*[
        scan_text_online(text, threshold=threshold, max_queries=max_queries, max_results_per_query=max_results_per_query)
        for text in texts
    ])


def is_available() -> bool:
    """True when both ddgs and beautifulsoup4 are installed."""
    return bool(_DDG_AVAILABLE and _BS4_AVAILABLE)
