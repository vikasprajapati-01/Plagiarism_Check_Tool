"""License and copyright detection service.

Detects open-source licenses in text/code content by matching against
known SPDX license patterns.

Logic preserved — identical to services/license_check.py.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from functools import partial
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False


# ── License pattern definitions ───────────────────────────────────────────────

@dataclass
class LicensePattern:
    """Definition of a license pattern for detection."""

    name: str
    spdx_id: str
    keywords: List[str]
    signature_text: str
    url: Optional[str] = None


LICENSE_PATTERNS: List[LicensePattern] = [
    LicensePattern(
        name="MIT License",
        spdx_id="MIT",
        keywords=["mit license", "permission is hereby granted, free of charge",
                  "the software is provided \"as is\"", "without warranty of any kind"],
        signature_text="Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files",
        url="https://opensource.org/licenses/MIT",
    ),
    LicensePattern(
        name="Apache License 2.0",
        spdx_id="Apache-2.0",
        keywords=["apache license", "version 2.0", "licensed under the apache license",
                  "without warranties or conditions of any kind"],
        signature_text="Licensed under the Apache License, Version 2.0",
        url="https://www.apache.org/licenses/LICENSE-2.0",
    ),
    LicensePattern(
        name="GNU General Public License v3.0",
        spdx_id="GPL-3.0",
        keywords=["gnu general public license", "version 3", "gpl-3.0", "gplv3",
                  "free software foundation", "either version 3 of the license"],
        signature_text="This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License",
        url="https://www.gnu.org/licenses/gpl-3.0.html",
    ),
    LicensePattern(
        name="GNU General Public License v2.0",
        spdx_id="GPL-2.0",
        keywords=["gnu general public license", "version 2", "gpl-2.0", "gplv2",
                  "free software foundation", "either version 2 of the license"],
        signature_text="This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2",
        url="https://www.gnu.org/licenses/gpl-2.0.html",
    ),
    LicensePattern(
        name="BSD 3-Clause License",
        spdx_id="BSD-3-Clause",
        keywords=["bsd 3-clause", "bsd-3-clause", "new bsd license", "modified bsd license",
                  "redistributions of source code must retain"],
        signature_text="Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met",
        url="https://opensource.org/licenses/BSD-3-Clause",
    ),
    LicensePattern(
        name="BSD 2-Clause License",
        spdx_id="BSD-2-Clause",
        keywords=["bsd 2-clause", "bsd-2-clause", "simplified bsd license", "freebsd license"],
        signature_text="Redistribution and use in source and binary forms, with or without modification, are permitted",
        url="https://opensource.org/licenses/BSD-2-Clause",
    ),
    LicensePattern(
        name="Mozilla Public License 2.0",
        spdx_id="MPL-2.0",
        keywords=["mozilla public license", "mpl-2.0", "mpl 2.0", "mpl version 2.0"],
        signature_text="This Source Code Form is subject to the terms of the Mozilla Public License",
        url="https://www.mozilla.org/en-US/MPL/2.0/",
    ),
    LicensePattern(
        name="ISC License",
        spdx_id="ISC",
        keywords=["isc license", "permission to use, copy, modify, and/or distribute"],
        signature_text="Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted",
        url="https://opensource.org/licenses/ISC",
    ),
    LicensePattern(
        name="The Unlicense",
        spdx_id="Unlicense",
        keywords=["unlicense", "this is free and unencumbered software", "public domain"],
        signature_text="This is free and unencumbered software released into the public domain",
        url="https://unlicense.org/",
    ),
    LicensePattern(
        name="Creative Commons Zero v1.0",
        spdx_id="CC0-1.0",
        keywords=["cc0", "creative commons zero", "public domain dedication", "cc0-1.0"],
        signature_text="To the extent possible under law, the author(s) have dedicated all copyright and related and neighboring rights to this software to the public domain worldwide",
        url="https://creativecommons.org/publicdomain/zero/1.0/",
    ),
    LicensePattern(
        name="Creative Commons Attribution 4.0",
        spdx_id="CC-BY-4.0",
        keywords=["creative commons attribution", "cc by 4.0", "cc-by-4.0"],
        signature_text="This work is licensed under the Creative Commons Attribution 4.0 International License",
        url="https://creativecommons.org/licenses/by/4.0/",
    ),
    LicensePattern(
        name="GNU Lesser General Public License v3.0",
        spdx_id="LGPL-3.0",
        keywords=["lgpl", "lesser general public license", "lgpl-3.0", "lgplv3"],
        signature_text="This library is free software; you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License",
        url="https://www.gnu.org/licenses/lgpl-3.0.html",
    ),
    LicensePattern(
        name="GNU Affero General Public License v3.0",
        spdx_id="AGPL-3.0",
        keywords=["agpl", "affero general public license", "agpl-3.0", "agplv3"],
        signature_text="This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License",
        url="https://www.gnu.org/licenses/agpl-3.0.html",
    ),
    LicensePattern(
        name="Eclipse Public License 2.0",
        spdx_id="EPL-2.0",
        keywords=["eclipse public license", "epl-2.0", "epl 2.0"],
        signature_text="Eclipse Public License - v 2.0",
        url="https://www.eclipse.org/legal/epl-2.0/",
    ),
    LicensePattern(
        name="Artistic License 2.0",
        spdx_id="Artistic-2.0",
        keywords=["artistic license", "artistic-2.0", "the artistic license 2.0"],
        signature_text="The Artistic License 2.0",
        url="https://opensource.org/licenses/Artistic-2.0",
    ),
]


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class LicenseMatch:
    """Result of a single license pattern match."""

    detected: bool
    license_name: Optional[str] = None
    spdx_id: Optional[str] = None
    confidence: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    signature_similarity: float = 0.0
    license_url: Optional[str] = None
    snippet: Optional[str] = None


@dataclass
class LicenseCheckResult:
    """Full result including all matched licenses."""

    has_license: bool
    licenses_detected: List[LicenseMatch] = field(default_factory=list)
    primary_license: Optional[LicenseMatch] = None
    total_matches: int = 0
    risk_level: str = "none"


# ── Core detection helpers ────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize text for pattern comparison."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()


def _keyword_score(text: str, keywords: List[str]) -> tuple:
    """Calculate keyword match score and return (score, matched_keywords)."""
    normalized = _normalize_text(text)
    matched = [kw for kw in keywords if _normalize_text(kw) in normalized]

    if not keywords:
        return 0.0, []

    return len(matched) / len(keywords), matched


def _signature_score(text: str, signature: str) -> float:
    """Calculate similarity between text and a license signature string."""
    if _RAPIDFUZZ_AVAILABLE:
        return fuzz.partial_ratio(_normalize_text(text), _normalize_text(signature)) / 100.0

    normalized_text = _normalize_text(text)
    normalized_sig = _normalize_text(signature)
    if normalized_sig in normalized_text:
        return 1.0
    words_sig = set(normalized_sig.split())
    words_text = set(normalized_text.split())
    if not words_sig:
        return 0.0
    return len(words_sig & words_text) / len(words_sig)


def _extract_snippet(text: str, keywords: List[str], max_length: int = 200) -> Optional[str]:
    """Extract a relevant text snippet containing license keywords."""
    normalized = text.lower()
    for kw in keywords:
        pos = normalized.find(kw.lower())
        if pos != -1:
            start = max(0, pos - 50)
            end = min(len(text), pos + max_length)
            snippet = text[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            return snippet
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def detect_license_sync(text: str, threshold: float = 0.3) -> LicenseCheckResult:
    """Detect open-source licenses in the given text synchronously."""
    if not text or not text.strip():
        return LicenseCheckResult(
            has_license=False,
            licenses_detected=[],
            primary_license=None,
            total_matches=0,
            risk_level="none",
        )

    matches: List[LicenseMatch] = []

    for pattern in LICENSE_PATTERNS:
        kw_score, matched_kws = _keyword_score(text, pattern.keywords)
        sig_score = _signature_score(text, pattern.signature_text)
        combined = (kw_score * 0.4) + (sig_score * 0.6)

        if combined >= threshold:
            matches.append(LicenseMatch(
                detected=True,
                license_name=pattern.name,
                spdx_id=pattern.spdx_id,
                confidence=round(combined, 4),
                matched_keywords=matched_kws,
                signature_similarity=round(sig_score, 4),
                license_url=pattern.url,
                snippet=_extract_snippet(text, pattern.keywords),
            ))

    matches.sort(key=lambda m: m.confidence, reverse=True)
    primary = matches[0] if matches else None

    if primary:
        if primary.confidence >= 0.8:
            risk_level = "high"
        elif primary.confidence >= 0.6:
            risk_level = "medium"
        elif primary.confidence >= 0.4:
            risk_level = "low"
        else:
            risk_level = "none"
    else:
        risk_level = "none"

    return LicenseCheckResult(
        has_license=bool(matches),
        licenses_detected=matches,
        primary_license=primary,
        total_matches=len(matches),
        risk_level=risk_level,
    )


async def detect_license(text: str, threshold: float = 0.3) -> LicenseCheckResult:
    """Async wrapper — runs detection in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(detect_license_sync, text, threshold))


async def detect_license_batch(
    texts: List[str],
    threshold: float = 0.3,
) -> List[LicenseCheckResult]:
    """Detect licenses in a batch of texts concurrently."""
    tasks = [detect_license(text, threshold) for text in texts]
    return await asyncio.gather(*tasks)


def get_supported_licenses() -> List[dict]:
    """Return list of supported licenses and their SPDX identifiers."""
    return [{"name": p.name, "spdx_id": p.spdx_id, "url": p.url} for p in LICENSE_PATTERNS]


def classify_license_risk(confidence: float) -> str:
    """Classify a license detection confidence score into a risk level string."""
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    if confidence >= 0.4:
        return "low"
    return "none"
