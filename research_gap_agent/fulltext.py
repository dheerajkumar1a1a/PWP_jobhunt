from __future__ import annotations

import io
import logging
import re
import warnings
from html import unescape
from urllib.request import Request, urlopen

from .enrichment import FREE_EMAIL_DOMAINS, PUBLISHER_DOMAINS, is_plausible_email, name_fragments


def fetch_bytes(url: str, timeout: int = 20) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "research-gap-agent/0.9 (public full text)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(), (r.headers.get("Content-Type") or "").lower()


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)


def extract_corresponding_email(text: str, full_name: str) -> str | None:
    """Find the author's own address in a paper's first-page correspondence block.

    Only the head of the text is inspected (corresponding-author emails are
    printed on page 1). The local part must contain a >=3-letter fragment of
    the author's name, and free-mail plus publisher domains are excluded.
    Returns None when nothing attributable is found — never a guess.
    """
    frags = name_fragments(full_name)
    if not frags or not text:
        return None
    for match in EMAIL_RE.finditer(text[:5000]):
        if not is_plausible_email(match.group(0), text, match.start()):
            continue
        email = match.group(0).rstrip(".,;:)")
        local, _, domain = email.partition("@")
        domain = domain.lower()
        if domain in FREE_EMAIL_DOMAINS or domain in PUBLISHER_DOMAINS:
            continue
        local_tokens = set(re.split(r"[^a-z0-9]+", local.lower()))
        if frags & local_tokens or any(len(f) >= 5 and f in local.lower() for f in frags):
            return email
    return None


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


def fetch_public_text(url: str | None, timeout: int = 20) -> str:
    """Fetch only explicitly public URLs; never bypasses a paywall."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        raw, content_type = fetch_bytes(url, timeout=timeout)
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
        # Semantic Scholar normalisation nests it; OpenAlex exposes pdf_url flat.
        pdf = (openalex_location.get("pdf") or {}).get("url") or openalex_location.get("pdf_url")
        if pdf:
            return pdf
    return None
