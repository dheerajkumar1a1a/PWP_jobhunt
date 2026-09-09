from __future__ import annotations

import re
import urllib.error
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def fetch_text(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={"User-Agent": "research-gap-agent/0.8 (public contact discovery)"})
    with urlopen(req, timeout=timeout) as r:
        content_type = (r.headers.get("Content-Type") or "").lower()
        if "text" not in content_type and "html" not in content_type:
            return ""
        return r.read(800_000).decode("utf-8", errors="ignore")


def public_emails_from_page(url: str) -> list[str]:
    if not url or urlparse(url).scheme not in {"http", "https"}:
        return []
    try:
        text = fetch_text(url)
    except (urllib.error.URLError, TimeoutError):
        return []
    emails = []
    for email in EMAIL_RE.findall(text):
        e = email.lower().rstrip(".,;:")
        if e not in emails and not any(x in e for x in ("example.com", "example.org", "noreply", "no-reply")):
            emails.append(e)
    return emails[:10]


def choose_institutional_email(emails: list[str], affiliation: str) -> str | None:
    aff = re.sub(r"[^a-z0-9]+", "", (affiliation or "").lower())
    personal_domains = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me", "protonmail.com"}
    for email in emails:
        domain = email.split("@", 1)[1]
        if domain in personal_domains:
            continue
        base = re.sub(r"[^a-z0-9]+", "", domain.split(".")[0])
        if base and (base in aff or any(x in domain for x in (".edu", ".ac.", ".edu."))):
            return email
    return None


def enrich(author: dict, urls: list[str]) -> dict:
    found: list[str] = []
    source = None
    for url in urls:
        for email in public_emails_from_page(url):
            if email not in found:
                found.append(email)
        candidate = choose_institutional_email(found, author.get("institution", ""))
        if candidate:
            source = url
            return {**author, "public_email": candidate, "verification_url": source, "contact_status": "verified_public_institutional"}
    return {**author, "public_email": None, "verification_url": None, "contact_status": "not_verified"}
