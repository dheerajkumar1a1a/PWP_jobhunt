from __future__ import annotations

from urllib.parse import quote

from . import scholarly

ORCID_API = "https://pub.orcid.org/v3.0"


def _best_author_match(results: list[dict], name: str) -> dict | None:
    target = " ".join(name.lower().split())
    exact = [a for a in results if " ".join(((a.get("display_name") or "").lower().split())) == target]
    pool = exact or results
    return max(pool, key=lambda a: (a.get("works_count") or 0, a.get("cited_by_count") or 0), default=None)


def search_openalex_author(name: str) -> dict | None:
    """Find the most likely OpenAlex author record. Returns None on no confident match."""
    url = "https://api.openalex.org/authors?search=" + quote(name) + "&per-page=5"
    try:
        results = scholarly.get_json(url).get("results", [])
    except Exception as exc:
        print(f"openalex author search failed for {name!r}: {exc}")
        return None
    return _best_author_match(results, name)


def orcid_researcher_urls(orcid: str) -> list[str]:
    """Personal/lab page URLs from the public ORCID record. Empty on any failure."""
    oid = (orcid or "").rsplit("/", 1)[-1].strip()
    if not oid:
        return []
    try:
        data = scholarly.get_json(f"{ORCID_API}/{quote(oid)}/researcher-urls")
    except Exception:
        return []
    urls = []
    for entry in data.get("researcher-url", []) or []:
        value = (entry.get("url") or {}).get("value", "")
        if isinstance(value, str) and value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    return urls


def backfill_profile_urls(name: str, affiliation: str = "") -> tuple[list[str], str]:
    """Backfill verifiable profile URLs for authors that arrived with none.

    Chain: OpenAlex author search → institution homepage(s) + ORCID researcher-urls.
    Returns (urls, institution_name). Refuses when a known affiliation
    contradicts the match (wrong-person guard). Verification policy is unchanged:
    callers still run the strict institutional check on fetched pages.
    """
    match = search_openalex_author(name)
    if not match:
        return [], ""
    institutions = match.get("last_known_institutions") or []
    inst_names = [i.get("display_name", "") for i in institutions if i.get("display_name")]
    if affiliation and inst_names and not any(
        affiliation.lower() in n.lower() or n.lower() in affiliation.lower() for n in inst_names
    ):
        return [], ""
    urls: list[str] = []
    for inst in institutions:
        homepage = inst.get("homepage_url") or ""
        if homepage.startswith(("http://", "https://")) and homepage not in urls:
            urls.append(homepage)
    orcid = (match.get("orcid") or "").strip()
    if orcid:
        for personal in orcid_researcher_urls(orcid):
            if personal not in urls:
                urls.append(personal)
        if orcid.startswith(("http://", "https://")) and orcid not in urls:
            urls.append(orcid)
    return urls, (inst_names[0] if inst_names else "")
