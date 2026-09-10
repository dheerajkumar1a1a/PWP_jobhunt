from __future__ import annotations

import json
import re
import urllib.error
from dataclasses import asdict, dataclass
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "research-gap-agent/0.8 (public academic profile enrichment; respectful rate)"
FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me", "protonmail.com"}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

# Filename tails the email regex can catch inside page markup (e.g. ORCID avatar URLs).
NON_EMAIL_TLDS = frozenset({
    "webp", "png", "jpg", "jpeg", "gif", "svg", "ico", "bmp", "tiff",
    "css", "js", "woff", "woff2", "mp4", "pdf", "zip",
})


def is_plausible_email(match_text: str, html: str, start: int) -> bool:
    """Reject regex hits that are URL path segments or asset filenames, not addresses."""
    email = match_text.rstrip(".,;:)")
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.rsplit(".", 1)[-1].lower() in NON_EMAIL_TLDS:
        return False
    if start > 0 and html[start - 1] == "/":
        return False
    return True

@dataclass(frozen=True)
class ProfileCandidate:
    author_name: str
    affiliation: str
    profile_url: str | None
    email: str | None
    source: str
    verified_public_institutional: bool


def fetch_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _institutional_email(email: str | None, affiliation: str, url: str) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower()
    if domain in FREE_EMAIL_DOMAINS:
        return False
    host = _domain(url)
    # Conservative: contact is only considered verified when the email domain
    # is the same as, or a subdomain of, the public profile host.
    return bool(host and (domain == host or domain.endswith("." + host)))


def extract_public_email(html: str) -> str | None:
    for match in EMAIL_RE.finditer(html or ""):
        if not is_plausible_email(match.group(0), html, match.start()):
            continue
        email = match.group(0).rstrip(".,;:)")
        domain = email.rsplit("@", 1)[1].lower()
        if domain not in FREE_EMAIL_DOMAINS:
            return email
    return None


def name_fragments(full_name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", (full_name or "").lower()) if len(t) >= 3}


def find_named_institutional_email(html: str, full_name: str, allowed_domains: set[str]) -> str | None:
    """First address in the page whose local part names the person and whose
    domain is one of the author's institutional domains. None otherwise —
    never a constructed guess."""
    frags = name_fragments(full_name)
    if not frags or not html:
        return None
    allowed = {d.lower() for d in allowed_domains}
    for match in EMAIL_RE.finditer(html):
        if not is_plausible_email(match.group(0), html, match.start()):
            continue
        email = match.group(0).rstrip(".,;:)")
        local, _, domain = email.partition("@")
        domain = domain.lower()
        if domain in FREE_EMAIL_DOMAINS or domain not in allowed:
            continue
        local_tokens = set(re.split(r"[^a-z0-9]+", local.lower()))
        if frags & local_tokens or any(len(f) >= 5 and f in local.lower() for f in frags):
            return email
    return None


def resolve_public_profile(name: str, affiliation: str, candidate_urls: list[str] | None = None) -> ProfileCandidate:
    """Inspect only supplied public profile URLs; never guess an email address or scrape arbitrary search engines.

    Tries every candidate URL and returns the first VERIFIED institutional
    contact. An unverified page (e.g. an institution homepage with no personal
    email) never shadows later URLs that might verify.
    """
    first_seen: ProfileCandidate | None = None
    for url in candidate_urls or []:
        try:
            if urlparse(url).scheme not in {"http", "https"}:
                continue
            html = fetch_text(url)
            email = extract_public_email(html)
            verified = _institutional_email(email, affiliation, url)
            if verified:
                return ProfileCandidate(name, affiliation, url, email, "public_profile_page", True)
            if first_seen is None:
                first_seen = ProfileCandidate(name, affiliation, url, None, "public_profile_page", False)
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return first_seen or ProfileCandidate(name, affiliation, None, None, "public_profile_page", False)


def to_dict(profile: ProfileCandidate) -> dict:
    return asdict(profile)
