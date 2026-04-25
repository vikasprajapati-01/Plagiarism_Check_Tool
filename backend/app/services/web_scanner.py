"""Web plagiarism scanner using DuckDuckGo + BeautifulSoup.

Core DuckDuckGo + BeautifulSoup pipeline preserved unchanged from
services/web_scan.py. Fingerprinting logic from services/web_fingerprint.py
is inlined here (that file is now deleted).

Additions on top of original logic:
  - retry loop with configurable WEB_SCAN_RETRIES around _search_ddg_sync
  - configurable timeout via WEB_SCAN_TIMEOUT passed to _fetch_page_text_sync
"""

import asyncio
import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.services.fuzzy_match import (
    jaccard_similarity,
    levenshtein_similarity,
    ngram_similarity,
)
from app.services.preprocessor import preprocess_text

logger = logging.getLogger(__name__)

# bs4 is needed to parse fetched pages
try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

# prefer the new `ddgs` package, fall back to the old name
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


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class WebMatch:
    """One matched web source for a scanned text."""

    url: str
    title: str
    snippet: str
    page_excerpt: str
    similarity_scores: dict = field(default_factory=dict)
    best_score: float = 0.0
    is_plagiarism: bool = False
    fingerprint: dict = field(default_factory=dict)


@dataclass
class WebScanResult:
    """Full result of scanning one text against the web."""

    submitted_text: str
    matches: List[WebMatch] = field(default_factory=list)
    is_plagiarism: bool = False
    best_score: float = 0.0
    best_url: Optional[str] = None
    total_urls_checked: int = 0
    error: Optional[str] = None


# ── Fingerprinting (inlined from web_fingerprint.py) ──────────────────────────

def _fingerprint(page_text: str) -> str:
    """SHA-256 of whitespace-normalised page text."""
    normalized = re.sub(r"\s+", " ", page_text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _extract_domain(url: str) -> str:
    """Root domain from a URL with www prefix stripped."""
    try:
        netloc = urlparse(url).netloc
        return re.sub(r"^www\.", "", netloc).lower()
    except Exception:
        return ""


def _extract_publish_date(html: str) -> Optional[datetime]:
    """Parse publication date from HTML meta tags (Open Graph / schema.org)."""
    if not _BS4_AVAILABLE or not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates = [
        soup.find("meta", property="article:published_time"),
        soup.find("meta", property="og:article:published_time"),
        soup.find("meta", attrs={"name": "date"}),
        soup.find("meta", attrs={"name": "pubdate"}),
        soup.find("meta", attrs={"name": "DC.date"}),
        soup.find("time", attrs={"itemprop": "datePublished"}),
        soup.find("time", attrs={"datetime": True}),
    ]

    for tag in candidates:
        if tag is None:
            continue
        raw = tag.get("content") or tag.get("datetime") or (tag.string or "").strip()
        if not raw:
            continue
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw[:19], fmt)
            except ValueError:
                continue

    return None


def _analyze_page(url: str, page_text: str, raw_html: str = "") -> dict:
    """Full fingerprint dict for a fetched page: content_hash, domain, published_at."""
    published = _extract_publish_date(raw_html)
    return {
        "content_hash": _fingerprint(page_text),
        "domain": _extract_domain(url),
        "published_at": published.isoformat() if published else None,
    }


# ── Core scan helpers (logic preserved from web_scan.py) ─────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def extract_search_queries(text: str, max_queries: int = 3, min_words: int = 6) -> List[str]:
    """Pick the longest sentences from the text to use as search queries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    valid = [s.strip() for s in sentences if len(s.split()) >= min_words]

    if not valid:
        words = text.split()
        valid = [" ".join(words[i:i + 8]) for i in range(0, len(words), 8)]

    valid.sort(key=len, reverse=True)
    return valid[:max_queries]


def _search_ddg_sync(query: str, max_results: int = 10) -> List[dict]:
    """Run a DuckDuckGo text search and return results as {href, title, body} dicts."""
    if not _DDG_AVAILABLE:
        raise RuntimeError("ddgs not installed. Run: pip install ddgs")

    try:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results)
    except Exception as exc:
        raise RuntimeError(f"DuckDuckGo search failed: {exc}") from exc

    return [
        {"href": item.get("href", ""), "title": item.get("title", ""), "body": item.get("body", "")}
        for item in (raw or [])
    ]


def _search_ddg_with_retry(
    query: str,
    max_results: int = 10,
    retries: int = 3,
) -> List[dict]:
    """Wrapper around _search_ddg_sync with exponential-backoff retry."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return _search_ddg_sync(query, max_results)
        except RuntimeError as exc:
            last_exc = exc
            if attempt < retries:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "DDG search attempt %d/%d failed: %s — retrying in %ds",
                    attempt, retries, exc, wait,
                )
                time.sleep(wait)
    raise RuntimeError(f"DDG search failed after {retries} attempts: {last_exc}") from last_exc


def _fetch_page_text_sync(url: str, timeout: int = 8) -> tuple:
    """Download a page and return (visible_text, raw_html). Both empty on failure."""
    if not _BS4_AVAILABLE:
        return "", ""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
        resp.raise_for_status()
        raw_html = resp.text
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        page_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
        return page_text, raw_html
    except Exception:
        return "", ""


def _windowed_similarity(query: str, page_text: str) -> dict:
    """Score similarity between query and the most similar window of the page."""
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
        if len(pq) <= 400 and len(ps) <= 400:
            best["levenshtein"] = max(
                best["levenshtein"], round(levenshtein_similarity(pq, ps), 3)
            )

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


# ── Public API ────────────────────────────────────────────────────────────────

async def scan_text_online(
    text: str,
    threshold: float = 0.5,
    max_queries: int = 2,
    max_results_per_query: int = 3,
    timeout: int = 8,
    retries: int = 3,
    max_scan_time: int = 30,
) -> WebScanResult:
    """Search the web for the given text and return all sources above the similarity threshold."""
    if not _DDG_AVAILABLE:
        return WebScanResult(
            submitted_text=text, error="ddgs not installed. Run: pip install ddgs"
        )
    if not _BS4_AVAILABLE:
        return WebScanResult(
            submitted_text=text,
            error="beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml",
        )

    loop = asyncio.get_event_loop()
    queries = extract_search_queries(text, max_queries=max_queries)

    seen_urls: set = set()
    search_results: list = []
    max_total_results = 10

    for query in queries:
        try:
            raw = await loop.run_in_executor(
                _EXECUTOR,
                lambda q=query: _search_ddg_with_retry(q, max_results_per_query, retries),
            )
        except RuntimeError as exc:
            return WebScanResult(submitted_text=text, error=str(exc))
        for r in raw:
            if len(search_results) >= max_total_results:
                break
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                search_results.append(r)
        if len(search_results) >= max_total_results:
            break

    total_checked = len(search_results)

    async def _process(result_dict: dict) -> Optional[WebMatch]:
        """Fetch and score one search result."""
        url = result_dict.get("href", "")
        title = result_dict.get("title", "")
        snippet = result_dict.get("body", "")

        try:
            page_text, raw_html = await asyncio.wait_for(
                loop.run_in_executor(
                    _EXECUTOR,
                    lambda u=url: _fetch_page_text_sync(u, timeout),
                ),
                timeout=timeout + 2,
            )
        except asyncio.TimeoutError:
            logger.warning("Page fetch timed out for URL: %s", url)
            page_text, raw_html = "", ""
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
            fingerprint=_analyze_page(url, page_text, raw_html),
        )

    try:
        raw_results = await asyncio.wait_for(
            asyncio.gather(
                *[_process(r) for r in search_results],
                return_exceptions=True,
            ),
            timeout=max_scan_time,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Web scan timed out after %ds for text: %.60s...",
            max_scan_time, text,
        )
        return WebScanResult(
            submitted_text=text,
            matches=[],
            is_plagiarism=False,
            best_score=0.0,
            best_url=None,
            total_urls_checked=total_checked,
            error=f"Scan timed out after {max_scan_time}s",
        )
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
    timeout: int = 8,
    retries: int = 3,
    max_scan_time: int = 30,
) -> List[WebScanResult]:
    """Run scan_text_online on multiple texts concurrently."""
    return await asyncio.gather(*[
        scan_text_online(
            text,
            threshold=threshold,
            max_queries=max_queries,
            max_results_per_query=max_results_per_query,
            timeout=timeout,
            retries=retries,
            max_scan_time=max_scan_time,
        )
        for text in texts
    ])


def is_available() -> bool:
    """True when both ddgs and beautifulsoup4 are installed."""
    return bool(_DDG_AVAILABLE and _BS4_AVAILABLE)
