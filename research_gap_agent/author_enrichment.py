from __future__ import annotations

from urllib.parse import urlparse

from .author_backfill import backfill_profile_urls
from .enrichment import resolve_public_profile, to_dict


def candidate_profile_urls(author: dict) -> list[str]:
    urls = []
    for key in ("profile_url", "orcid", "homepage"):
        value = author.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            urls.append(value)
    return urls


def enrich_author(author: dict) -> dict:
    name = (author.get("name") or "").strip()
    affiliation = (author.get("institution") or "").strip()
    urls = candidate_profile_urls(author)
    backfilled = False
    if not urls and name:
        urls, backfilled_institution = backfill_profile_urls(name, affiliation)
        backfilled = bool(urls)
        if not affiliation and backfilled_institution:
            affiliation = backfilled_institution
    profile = resolve_public_profile(name, affiliation, urls)
    result = dict(author)
    if not (result.get("institution") or "").strip() and affiliation:
        result["institution"] = affiliation
    result.update({
        "profile_url": profile.profile_url,
        "public_email": profile.email,
        "contact_source": profile.source,
        "verified_public_institutional": profile.verified_public_institutional,
        "profile_backfilled": backfilled,
    })
    return result
