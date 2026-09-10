from __future__ import annotations

import io
import logging
import re
import warnings
from html import unescape
from urllib.request import Request, urlopen


def fetch_bytes(url: str, timeout: int = 20) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "research-gap-agent/0.9 (public full text)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(), (r.headers.get("Content-Type") or "").lower()


def extract_html_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def extract_pdf_text(raw: bytes) -> str:
    if not raw.startswith(b"%PDF-"):
        # Publisher served an HTML error/landing page instead of a PDF
        # (pypdf would log "invalid pdf header: b'<!doc'" and raise).
        return ""
    try:
        from pypdf import PdfReader
        logger = logging.getLogger("pypdf")
        level = logger.level
        logger.setLevel(logging.CRITICAL)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                reader = PdfReader(io.BytesIO(raw))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
        finally:
            logger.setLevel(level)
    except Exception:
        return ""


def fetch_public_text(url: str | None) -> str:
    """Fetch only explicitly public URLs; never bypasses a paywall."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        raw, content_type = fetch_bytes(url)
    except OSError:
        # URLError, TimeoutError, ConnectionResetError, ...: a fulltext
        # fetch must never crash the scan.
        return ""
    if "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf"):
        if raw.lstrip()[:1] == b"<":
            # Same public URL, but the body is a landing page: salvage its text.
            return extract_html_text(raw)
        return extract_pdf_text(raw)
    if "html" in content_type or "text" in content_type:
        return extract_html_text(raw)
    return ""


def locate_gap_sentences(text: str, max_sentences: int = 8) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    keywords = re.compile(r"limitation|limited|challenge|future work|further work|need to|requires?|destructive|laborious|expensive|portable|non[- ]destructive|smartphone|cannot|remains?", re.I)
    return [s.strip()[:700] for s in sentences if keywords.search(s)][:max_sentences]


def find_public_pdf(doi: str | None, openalex_location: dict | None = None) -> str | None:
    if openalex_location:
        pdf = (openalex_location.get("pdf") or {}).get("url")
        if pdf:
            return pdf
    return None
