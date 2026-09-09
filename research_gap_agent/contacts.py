from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

@dataclass(frozen=True)
class ContactCandidate:
    name: str
    affiliation: str
    email: str | None
    verification_url: str | None
    source: str
    verified_public_institutional: bool


def is_institutional_email(email: str | None, affiliation: str = "") -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower().strip()
    generic = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me", "protonmail.com", "icloud.com"}
    if domain in generic:
        return False
    aff = re.sub(r"[^a-z0-9]+", "", affiliation.lower())
    dom = re.sub(r"[^a-z0-9]+", "", domain.split(".")[0])
    return bool(dom and (dom in aff or any(x in domain for x in (".edu", ".ac.", ".edu."))))


def extract_public_emails(url: str, timeout: int = 20) -> list[str]:
    req = Request(url, headers={"User-Agent": "research-gap-agent/0.2", "Accept": "text/html,*/*"})
    with urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return sorted(set(EMAIL_RE.findall(html)))


def verify_candidate(name: str, affiliation: str, email: str | None, verification_url: str | None) -> ContactCandidate:
    parsed_ok = False
    if verification_url:
        try:
            parsed_ok = urlparse(verification_url).scheme in {"http", "https"}
        except ValueError:
            parsed_ok = False
    verified = bool(parsed_ok and is_institutional_email(email, affiliation))
    return ContactCandidate(name, affiliation, email if verified else None, verification_url if verified else None, "public_institutional_page", verified)
