from __future__ import annotations

from urllib.parse import urlparse

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
    profile = resolve_public_profile(name, affiliation, urls)
    result = dict(author)
    result.update({
        "profile_url": profile.profile_url,
        "public_email": profile.email,
        "contact_source": profile.source,
        "verified_public_institutional": profile.verified_public_institutional,
    })
    return result
