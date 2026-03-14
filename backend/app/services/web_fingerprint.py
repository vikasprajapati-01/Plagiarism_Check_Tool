"""Web page fingerprinting: content hashing, domain extraction, and publication date detection.

Used alongside web_scan.py to identify known sources and track when content was published.
"""

import hashlib
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


def fingerprint(page_text: str) -> str:
    """SHA-256 of whitespace-normalized page text.

    Two pages with identical content but different spacing hash to the same value.
    """
    normalized = re.sub(r"\s+", " ", page_text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_domain(url: str) -> str:
    """Root domain from a URL, www prefix stripped.

    'https://www.example.com/page/1' → 'example.com'
    Returns empty string on parse failure.
    """
    try:
        netloc = urlparse(url).netloc
        return re.sub(r"^www\.", "", netloc).lower()
    except Exception:
        return ""


def extract_publish_date(html: str) -> Optional[datetime]:
    """Parse the publication date from HTML meta tags.

    Checks Open Graph, schema.org, and common meta name patterns in order.
    Returns a datetime on success, None if nothing parseable is found.
    """
    if not _BS4_AVAILABLE or not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Ordered by reliability — first match wins
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


def analyze(url: str, page_text: str, raw_html: str = "") -> dict:
    """Full fingerprint analysis of a fetched page.

    Returns:
        content_hash — SHA-256 of normalized page text
        domain       — root domain (e.g. 'example.com')
        published_at — ISO-8601 date string or null
    """
    published = extract_publish_date(raw_html)
    return {
        "content_hash": fingerprint(page_text),
        "domain": extract_domain(url),
        "published_at": published.isoformat() if published else None,
    }
