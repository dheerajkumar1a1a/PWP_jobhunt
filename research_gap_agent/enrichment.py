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
    for match in EMAIL_RE.findall(html):
        email = match.rstrip(".,;:)")
        domain = email.rsplit("@", 1)[1].lower()
        if domain not in FREE_EMAIL_DOMAINS:
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
