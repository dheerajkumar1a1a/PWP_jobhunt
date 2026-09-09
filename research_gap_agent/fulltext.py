from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = "research-gap-agent/0.3 (open-access retrieval; respectful rate)"


def get_json(url: str):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def find_public_pdf(doi: str | None, openalex_location: dict | None = None) -> str | None:
    """Return a public PDF URL when the metadata explicitly exposes one.

    This helper deliberately avoids bypassing paywalls or scraping publisher pages.
    """
    if openalex_location:
        pdf = (openalex_location.get("pdf") or {}).get("url")
        if pdf:
            return pdf
    if not doi:
        return None
    # Crossref metadata is useful for locating publisher landing pages, but this
    # function does not assume a landing page is a downloadable PDF.
    url = f"https://api.crossref.org/works/{quote(doi, safe='') }"
    try:
        item = get_json(url).get("message", {})
    except Exception:
        return None
    for link in item.get("link", []):
        ctype = (link.get("content-type") or "").lower()
        if "pdf" in ctype and link.get("URL"):
            return link["URL"]
    return None
